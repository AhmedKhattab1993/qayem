"""Qayem CLI: parse Tier-1 sources into one unified property database."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from .config import DEFAULT_MIN_INTERVAL
from .db import get_engine, init_db, session_scope
from .enrichment import BATCH_SIZE, PROMPT_VERSION, claim_batch, count_eligible, revoke_outdated, run_batches
from .http_client import Fetcher
from .models import ParseRun, Property, PropertyEnrichment, PropertyVersion, utcnow
from .sources import SOURCE_REGISTRY
from .upsert import (
    SyncStats, backfill_from_description, known_versions, mark_removals, renormalize, touch_present,
    upsert_listing,
)

app = typer.Typer(
    name="qayem",
    help="Egyptian secondary-market (resale) property listing parsers with a unified database.",
    no_args_is_help=True,
)
console = Console()


def _resolve_since(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise typer.BadParameter(
            f"invalid date {value!r} — use YYYY-MM-DD or full ISO format"
        ) from exc


@app.command()
def init() -> None:
    """Create the SQLite database and tables."""
    engine = get_engine()
    init_db(engine)
    from .config import db_path

    console.print(f"[green]Database ready:[/green] {Path(db_path()).resolve()}")


RENORMALIZERS = {"nawy": "qayem.sources.nawy:parse_unit", "nawy_primary": "qayem.sources.nawy:parse_primary_unit"}
# Sources without a re-parseable payload whose description is a generated template.
DESCRIPTION_BACKFILLS = {"semsar": "qayem.sources.semsar:parse_description"}


@app.command("renormalize")
def renormalize_command(
    source: str = typer.Argument("nawy", help=f"Source to re-parse: {', '.join([*RENORMALIZERS, *DESCRIPTION_BACKFILLS])}."),
) -> None:
    """Re-parse stored raw payloads (or template descriptions) with the current parser.

    No fetching, no version rows.
    """
    from importlib import import_module

    if source in DESCRIPTION_BACKFILLS:
        module, name = DESCRIPTION_BACKFILLS[source].split(":")
        engine = get_engine()
        init_db(engine)
        with session_scope(engine) as session:
            rows, changed = backfill_from_description(session, source, getattr(import_module(module), name))
        console.print(f"[green]{source}:[/green] read {rows} stored descriptions, {changed} rows filled")
        return
    if source not in RENORMALIZERS:
        available = ", ".join([*RENORMALIZERS, *DESCRIPTION_BACKFILLS])
        raise typer.BadParameter(f"{source!r} keeps no re-parseable payload. Available: {available}")

    module, name = RENORMALIZERS[source].split(":")
    engine = get_engine()
    init_db(engine)
    with session_scope(engine) as session:
        rows, changed = renormalize(session, source, getattr(import_module(module), name))
    console.print(f"[green]{source}:[/green] re-parsed {rows} stored payloads, {changed} rows changed")


@app.command("enrich-descriptions")
def enrich_descriptions(
    batches: int = typer.Option(1, min=0, help=f"Number of {BATCH_SIZE}-listing batches; 0 runs until exhausted."),
    source: str | None = typer.Option(None, help="Limit to one source, such as opensooq."),
    retry_failed: bool = typer.Option(False, help="Explicitly retry only failed listings; successful listings stay untouched."),
    workers: int = typer.Option(4, min=1, max=16, help="Maximum concurrent Codex calls (one batch each)."),
    dry_run: bool = typer.Option(False, help="Show the next batch without invoking Codex or claiming rows."),
    since: datetime | None = typer.Option(None, formats=["%Y-%m-%d"], help="Only listings first seen on or after this date."),
) -> None:
    """Fill missing listing facts from title and description (gpt-6-sol, batched).

    Only listings the website could show are sent: free-text sources, for
    sale in EGP within the price range, a valued unit type, a missing
    website/valuation field, and text that mentions it. Newest first.
    """
    from .config import db_path

    if source and source not in SOURCE_REGISTRY:
        raise typer.BadParameter(f"unknown source {source!r}. Available: {', '.join(SOURCE_REGISTRY)}")
    if not db_path().is_file():
        console.print(f"[red]Database not found:[/red] {db_path().resolve()}")
        raise typer.Exit(1)
    engine = get_engine()
    if dry_run:
        tasks = claim_batch(engine, source, dry_run=True, retry_failed=retry_failed, since=since)
        for task in tasks:
            console.print(f"{task.property_id}: {', '.join(task.missing)}")
        console.print(f"[dim]{len(tasks)} of {BATCH_SIZE} candidates in the next batch[/dim]")
        if not retry_failed:
            console.print(f"[dim]{count_eligible(engine, source, since)} listings eligible in total[/dim]")
        return
    init_db(engine)  # adds the durable enrichment table to an existing database

    def report_batch(number, batch_results) -> None:
        completed = sum(result.status == "done" for result in batch_results)
        filled = sum(result.applied for result in batch_results)
        console.print(f"Batch {number}: {len(batch_results)} listings, "
                      f"{completed} done, {filled} columns filled.")

    try:
        results = run_batches(
            engine, batches, source, on_batch=report_batch,
            retry_failed=retry_failed, workers=workers, since=since,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    done = sum(result.status == "done" for result in results)
    failed = len(results) - done
    filled = sum(result.applied for result in results)
    console.print(f"Processed {len(results)} listings in batches of {BATCH_SIZE}: "
                  f"{done} done, {failed} failed, {filled} columns filled.")
    for result in results:
        if result.error:
            console.print(f"  [yellow]{result.property_id}:[/yellow] {result.error}")


@app.command("enrich-revoke")
def enrich_revoke(
    dry_run: bool = typer.Option(False, help="Only report what would be reverted."),
) -> None:
    """Undo fills from earlier enrichment prompts and make those listings eligible again.

    A column is reset only while it still holds the value the old enrichment
    wrote. Every reverted value is written to logs/enrich-revoke-*.json first.
    """
    from .config import db_path

    if not db_path().is_file():
        console.print(f"[red]Database not found:[/red] {db_path().resolve()}")
        raise typer.Exit(1)
    engine = get_engine()
    init_db(engine)
    preview = revoke_outdated(engine, dry_run=True)
    with session_scope(engine) as session:
        records = session.scalar(
            select(func.count()).select_from(PropertyEnrichment)
            .where((PropertyEnrichment.prompt_version.is_(None))
                   | (PropertyEnrichment.prompt_version != PROMPT_VERSION)))
    console.print(f"{records} records from earlier prompts; {len(preview)} filled values to revert.")
    if dry_run or not records:
        return
    audit = Path("logs") / f"enrich-revoke-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    audit.parent.mkdir(exist_ok=True)
    audit.write_text(json.dumps(preview, ensure_ascii=False, indent=1), encoding="utf-8")
    reverted = revoke_outdated(engine)
    console.print(f"Reverted {len(reverted)} values and removed {records} records. Audit: {audit}")


@app.command("enrich-status")
def enrich_status() -> None:
    """Show durable description-enrichment attempt counts."""
    from .config import db_path

    if not db_path().is_file():
        console.print(f"[red]Database not found:[/red] {db_path().resolve()}")
        raise typer.Exit(1)
    engine = get_engine()
    init_db(engine)
    with session_scope(engine) as session:
        counts = session.execute(
            select(PropertyEnrichment.status, func.count())
            .group_by(PropertyEnrichment.status)
        ).all()
        for state, count in counts:
            console.print(f"{state}: {count}")
        if not counts:
            console.print("No properties invoked yet.")


@app.command()
def parse(
    source: str = typer.Argument(..., help=f"Source name or 'all'. One of: {', '.join(SOURCE_REGISTRY)} | all"),
    city: str | None = typer.Option(None, help="City scope (opensooq, aqarmap)."),
    category: str | None = typer.Option(None, help="Category scope (opensooq, semsar)."),
    governorate: str | None = typer.Option(None, help="Governorate scope (reserved)."),
    max_pages: int | None = typer.Option(None, help="Cap list pages per source. A capped run never marks removals."),
    max_details: int | None = typer.Option(None, help="Cap detail-page fetches (gpm, semsar, coldwellbanker)."),
    details: bool | None = typer.Option(
        None, "--details/--no-details",
        help="Fetch detail pages where supported. Default: each source's own default "
        "(gpm: yes with a 100-detail budget, semsar: no, coldwellbanker: yes with a 200-detail budget).",
    ),
    dry_run: bool = typer.Option(False, help="Fetch and parse, but write nothing."),
    min_interval: float = typer.Option(DEFAULT_MIN_INTERVAL, help="Min seconds between requests to a host."),
) -> None:
    """Parse one source (or all) and sync results into the database."""
    names = list(SOURCE_REGISTRY) if source == "all" else [source]
    for name in names:
        if name not in SOURCE_REGISTRY:
            raise typer.BadParameter(
                f"unknown source {name!r}. Available: {', '.join(SOURCE_REGISTRY)} | all"
            )

    engine = get_engine()
    if not dry_run:
        init_db(engine)

    for name in names:
        _run_source(engine, name, dict(
            city=city, category=category, governorate=governorate,
            max_pages=max_pages, max_details=max_details, details=details,
        ), dry_run=dry_run, min_interval=min_interval)


def _run_source(engine, name: str, params: dict, dry_run: bool, min_interval: float,
                budget_minutes: float | None = None) -> str:
    """Fetch one source scope and sync it. Returns the run status. A time budget stops
    the scope early (recorded as partial, so it never marks removals); an unexpected
    error is recorded as a failed run instead of leaving it 'running'."""
    params = {k: v for k, v in params.items() if v is not None}
    lock = source_lock(name)
    if lock is None:
        console.print(f"[yellow]{name}: another run of this source is in progress; skipped[/yellow]")
        return "skipped"
    run_started = utcnow()
    deadline = time.monotonic() + budget_minutes * 60 if budget_minutes else None
    run_id = None
    if not dry_run:
        with session_scope(engine) as session:
            run = ParseRun(source=name, started_at=run_started, status="running", params=params)
            session.add(run)
            session.flush()
            run_id = run.id

    stats = SyncStats()
    status = "completed"

    source_cls = SOURCE_REGISTRY[name]
    extra: dict = {}
    if source_cls.wants_known and not dry_run:
        with session_scope(engine) as session:
            extra["known"] = known_versions(session, name)

    with Fetcher(min_interval=min_interval) as fetcher:
        src = source_cls(fetcher, **params, **extra)

        def process(session) -> None:
            """Fetch + upsert all listings; `session=None` means dry-run."""
            nonlocal status
            batch: list = []
            batch_started = time.monotonic()

            def flush() -> None:
                # Listings are written in one short transaction per batch, never while the
                # source waits on the network, so concurrent writers are not starved.
                nonlocal batch_started
                if session is not None and batch:
                    for item in batch:
                        action = upsert_listing(session, name, item)
                        if action == "created":
                            stats.created += 1
                        elif action == "updated":
                            stats.updated += 1
                        elif action == "unchanged":
                            stats.unchanged += 1
                        else:
                            stats.relisted += 1
                    session.commit()
                batch.clear()
                batch_started = time.monotonic()

            unique: set[str] = set()
            for listing in src.fetch():
                stats.seen += 1
                unique.add(listing.source_listing_id)
                if not batch:
                    batch_started = time.monotonic()
                batch.append(listing)
                if len(batch) >= 100 or time.monotonic() - batch_started > 10:
                    flush()
                if deadline and time.monotonic() > deadline:
                    src.errors.append(f"time budget of {budget_minutes:g} min reached")
                    break
            flush()
            if stats.seen >= 200 and len(unique) * 2 < stats.seen:
                # the same listings over and over: pagination is broken, not the market
                src.errors.append(f"only {len(unique)} distinct listings in {stats.seen} seen: paging repeats")
                src.scopes_completed.clear()  # nothing this run saw can justify a removal

            if session is not None and src.present_ids:
                session.commit()
                touch_present(session, name, src.present_ids, utcnow())
            # Guarded removals: only scopes whose crawl completed naturally
            # (pagination end reached, no errors) mark their unseen listings
            # as removed — never a scope this run didn't fully cover.
            if session is not None:
                for scope in sorted(src.scopes_completed):
                    stats.marked_removed += mark_removals(session, name, scope, run_started)
            if not src.complete or src.errors:
                status = "partial" if stats.seen > 0 else "failed"

        try:
            if dry_run:
                process(None)
            else:
                with session_scope(engine) as session:
                    process(session)
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop a crawl
            src.errors.append(f"crashed: {type(exc).__name__}: {exc}")
            status = "failed"
        if not dry_run:
            with session_scope(engine) as session:
                run = session.get(ParseRun, run_id)
                run.finished_at = utcnow()
                run.status = status
                run.pages_fetched = src.pages_fetched
                run.seen = stats.seen
                run.created = stats.created
                run.updated = stats.updated
                run.unchanged = stats.unchanged
                run.marked_removed = stats.marked_removed
                run.errors = src.errors or None

    _print_run_summary(name, status, stats, src.pages_fetched, src.errors, dry_run)
    lock.close()
    return status


def source_lock(name: str):
    """Exclusive, non-blocking per-source lock (released when the file closes or the process exits)."""
    import fcntl

    from .config import db_path

    directory = Path(db_path()).resolve().parent / ".qayem-locks"
    directory.mkdir(exist_ok=True)
    handle = open(directory / f"{name}.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


@app.command()
def crawl(
    only: list[str] = typer.Option(None, "--only", help="Limit to these sources (repeatable)."),
    min_interval: float = typer.Option(DEFAULT_MIN_INTERVAL, help="Min seconds between requests to a host."),
) -> None:
    """Run the full production crawl plan: every source scope, each with a time budget."""
    from .crawl import PLAN, close_abandoned_runs

    engine = get_engine()
    init_db(engine)
    with session_scope(engine) as session:
        closed = close_abandoned_runs(session, utcnow())
    if closed:
        console.print(f"[yellow]Closed {closed} abandoned run(s) as failed[/yellow]")
    unknown = set(only or []) - set(SOURCE_REGISTRY)
    if unknown:
        raise typer.BadParameter(f"unknown source(s): {', '.join(sorted(unknown))}")
    outcomes: dict[str, int] = {}
    for scope in PLAN:
        if only and scope.source not in only:
            continue
        console.print(f"[bold]→ {scope.label}[/bold] (budget {scope.budget_minutes} min)")
        status = _run_source(engine, scope.source, dict(scope.params), dry_run=False,
                             min_interval=scope.min_interval or min_interval, budget_minutes=scope.budget_minutes)
        outcomes[status] = outcomes.get(status, 0) + 1
    console.print(f"Crawl finished: {outcomes}")


@app.command()
def health(
    write: Path | None = typer.Option(None, help="Also write the report as JSON to this path."),
) -> None:
    """Judge every scheduled source from its run history. Exits 1 if any source needs attention."""
    from .crawl import source_health

    engine = get_engine()
    init_db(engine)
    now = utcnow()
    with session_scope(engine) as session:
        report = source_health(session, now)
    table = Table(title="Source health", show_header=True, header_style="bold")
    for column in ("source", "state", "last run", "status", "last listings", "detail"):
        table.add_column(column)
    colors = {"ok": "green", "running": "cyan", "stale": "yellow", "dropped": "yellow", "failing": "red", "never": "red"}
    for item in report:
        table.add_row(item.source, f"[{colors[item.state]}]{item.state}[/]",
                      item.last_run.strftime("%Y-%m-%d %H:%M") if item.last_run else "-",
                      item.last_status or "-",
                      item.last_success.strftime("%Y-%m-%d %H:%M") if item.last_success else "-", item.detail)
    console.print(table)
    if write:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(json.dumps({"checked_at": now.isoformat(),
                                     "sources": [item.as_dict() for item in report]}, indent=2))
    if any(item.state not in ("ok", "running") for item in report):
        raise typer.Exit(1)


def _print_run_summary(name, status, stats, pages, errors, dry_run) -> None:
    label = f"[bold]{name}[/bold]" + (" [dim](dry run)[/dim]" if dry_run else "")
    color = {"completed": "green", "partial": "yellow", "failed": "red"}.get(status, "white")
    table = Table(title=f"Parse run — {label}", show_header=True, header_style="bold")
    table.add_column("status", style=color)
    table.add_column("pages")
    table.add_column("seen")
    table.add_column("created", style="green")
    table.add_column("updated", style="yellow")
    table.add_column("unchanged", style="dim")
    table.add_column("relisted", style="cyan")
    table.add_column("removed", style="red")
    table.add_row(
        status, str(pages), str(stats.seen), str(stats.created), str(stats.updated),
        str(stats.unchanged), str(stats.relisted), str(stats.marked_removed),
    )
    console.print(table)
    for err in errors[:5]:
        console.print(f"  [red]·[/red] {err}")
    if errors and len(errors) > 5:
        console.print(f"  [red]· … {len(errors) - 5} more errors[/red]")


@app.command()
def status() -> None:
    """Per-source: last run outcome and database totals by status."""
    engine = get_engine()
    with session_scope(engine) as session:
        table = Table(title="Sources", show_header=True, header_style="bold")
        for col, key in [
            ("source", "source"), ("last run", "started"), ("status", "status"),
            ("seen", None), ("new", None), ("updated", None), ("removed", None),
            ("active in db", None), ("removed in db", None),
        ]:
            table.add_column(col)
        for name in SOURCE_REGISTRY:
            last = session.execute(
                select(ParseRun).where(ParseRun.source == name)
                .order_by(ParseRun.started_at.desc()).limit(1)
            ).scalar_one_or_none()
            active = session.execute(
                select(func.count()).select_from(Property)
                .where(Property.source == name, Property.status == "active")
            ).scalar_one()
            removed = session.execute(
                select(func.count()).select_from(Property)
                .where(Property.source == name, Property.status == "removed")
            ).scalar_one()
            if last:
                table.add_row(
                    name, str(last.started_at), last.status or "-", str(last.seen),
                    str(last.created), str(last.updated), str(last.marked_removed),
                    str(active), str(removed),
                )
            else:
                table.add_row(name, "-", "-", "-", "-", "-", "-", str(active), str(removed))
        console.print(table)


@app.command("list")
def list_properties(
    source: str | None = typer.Option(None, help="Filter by source."),
    property_status: str = typer.Option("active", "--status", help="active | removed | all"),
    city: str | None = typer.Option(None),
    min_price: float | None = typer.Option(None),
    max_price: float | None = typer.Option(None),
    changed_since: str | None = typer.Option(None, help="Only rows updated since YYYY-MM-DD."),
    is_resale: bool | None = typer.Option(None, "--resale/--any", help="Filter resale-classified only."),
    limit: int = typer.Option(50, help="Max rows."),
    format: str = typer.Option("table", "--format", help="table | json"),
) -> None:
    """Browse the unified property database."""
    engine = get_engine()
    with session_scope(engine) as session:
        q = select(Property)
        if source:
            q = q.where(Property.source == source)
        if property_status != "all":
            q = q.where(Property.status == property_status)
        if city:
            q = q.where(Property.city.ilike(f"%{city}%"))
        if min_price is not None:
            q = q.where(Property.price >= min_price)
        if max_price is not None:
            q = q.where(Property.price <= max_price)
        since = _resolve_since(changed_since)
        if since:
            q = q.where(Property.updated_at >= since)
        if is_resale:
            q = q.where(Property.is_resale == True)  # noqa: E712
        rows = session.execute(q.order_by(Property.updated_at.desc()).limit(limit)).scalars().all()

        if format == "json":
            console.print_json(json.dumps([_row_dict(r) for r in rows], default=str))
            return
        table = Table(title=f"{len(rows)} properties", show_header=True, header_style="bold")
        for col in ["id", "source", "src id", "title", "type", "price", "area", "beds",
                    "city", "resale", "status"]:
            table.add_column(col, overflow="fold")
        for r in rows:
            table.add_row(
                str(r.id), r.source, r.source_listing_id,
                (r.title or "")[:48], r.property_type or "-",
                f"{r.price:,.0f} {r.currency}" if r.price else "-",
                str(r.area_m2 or "-"), str(r.bedrooms or "-"),
                r.city or r.district or "-",
                {True: "yes", False: "no", None: "?"}[r.is_resale],
                r.status,
            )
        console.print(table)


def _row_dict(r: Property) -> dict:
    return {
        "id": r.id, "source": r.source, "source_listing_id": r.source_listing_id,
        "url": r.url, "title": r.title, "purpose": r.purpose,
        "property_type": r.property_type, "is_resale": r.is_resale,
        "resale_evidence": r.resale_evidence, "price": r.price, "currency": r.currency,
        "area_m2": r.area_m2, "bedrooms": r.bedrooms, "bathrooms": r.bathrooms,
        "finishing": r.finishing, "compound": r.compound, "developer": r.developer,
        "governorate": r.governorate, "city": r.city, "district": r.district,
        "seller_type": r.seller_type, "phone": r.phone, "posted_at": r.posted_at,
        "status": r.status, "first_seen_at": r.first_seen_at, "last_seen_at": r.last_seen_at,
        "removed_at": r.removed_at,
    }


@app.command()
def show(property_id: int = typer.Argument(..., help="Database id from `qayem list`.")) -> None:
    """One property with its full change history."""
    engine = get_engine()
    with session_scope(engine) as session:
        prop = session.get(Property, property_id)
        if prop is None:
            console.print(f"[red]No property with id {property_id}[/red]")
            raise typer.Exit(1)
        console.print_json(json.dumps(_row_dict(prop), default=str, ensure_ascii=False))
        versions = session.execute(
            select(PropertyVersion).where(PropertyVersion.property_id == property_id)
            .order_by(PropertyVersion.captured_at)
        ).scalars().all()
        table = Table(title="History", show_header=True, header_style="bold")
        table.add_column("when")
        table.add_column("change")
        table.add_column("changed fields")
        for v in versions:
            changed = ", ".join(v.changed_fields.keys()) if v.changed_fields else "-"
            table.add_row(str(v.captured_at), v.change_type, changed)
        console.print(table)


@app.command()
def removed(
    since: str | None = typer.Option(None, help="Only removals since YYYY-MM-DD."),
    source: str | None = typer.Option(None),
) -> None:
    """Listings that disappeared from their source (state-tracking audit)."""
    engine = get_engine()
    with session_scope(engine) as session:
        q = select(Property).where(Property.status == "removed")
        since_dt = _resolve_since(since)
        if since_dt:
            q = q.where(Property.removed_at >= since_dt)
        if source:
            q = q.where(Property.source == source)
        rows = session.execute(q.order_by(Property.removed_at.desc()).limit(200)).scalars().all()
        table = Table(title=f"{len(rows)} removed listings", show_header=True, header_style="bold")
        for col in ["id", "source", "title", "price", "removed at", "url"]:
            table.add_column(col, overflow="fold")
        for r in rows:
            table.add_row(
                str(r.id), r.source, (r.title or "")[:44],
                f"{r.price:,.0f}" if r.price else "-", str(r.removed_at), r.url or "-",
            )
        console.print(table)


if __name__ == "__main__":
    app()
