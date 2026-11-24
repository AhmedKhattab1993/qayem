"""FastAPI application serving the Qayem read-only website and JSON API."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from threading import Thread
from typing import Collection, Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import editorial, guide_api, seo
from .config import crawled_sources, db_path as configured_db_path, market_sources
from .growth import Growth, LocalDatabase, LocalHttp, Settings, client_details, growth_router
from .valuation import slug
from .website_data import Catalog, CatalogUnavailable, evaluate, evaluate_query, public_unit, url_key

from .web_common import RANK_MIN_COMPOUND, RANK_MIN_DEVELOPER, matches, page_of, sort_entities



_CONFIGURED = object()


class SnapshotPublic:
    """The local catalogue for the growth routes (cloud_web.Store in the Worker)."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    async def newest_unit_id(self) -> int:
        return max((r["id"] for r in self.catalog.snapshot().default), default=0)

    async def unit(self, unit_id: int) -> dict | None:
        record = self.catalog.snapshot().records.get(unit_id)
        return public_unit(record) if record else None


def create_app(db_path: str | Path | None = None, static_dir: str | Path | None = None,
               refresh_seconds: float | None = None, sources: Collection[str] | None | object = _CONFIGURED,
               leads_db: str | Path | None | object = _CONFIGURED, http=None, settings: Settings | None = None) -> FastAPI:
    if refresh_seconds is None:
        refresh_seconds = float(os.environ.get("QAYEM_REFRESH_SECONDS", "300"))
    if sources is _CONFIGURED:
        sources = crawled_sources()  # benchmark rows are read for launch prices, never listed
    catalog = Catalog(db_path if db_path is not None else configured_db_path(), refresh_seconds, sources,
                      market_sources() if sources is not None else ())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Thread(target=catalog.warm, name="qayem-catalog-warm", daemon=True).start()  # the first fit takes seconds
        yield

    app = FastAPI(title="Qayem Market Evaluation", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.catalog = catalog
    static_root = Path(static_dir) if static_dir is not None else Path(__file__).resolve().parents[2] / "web" / "dist"
    static_root = static_root.resolve()
    if leads_db is _CONFIGURED:
        leads_db = os.environ.get("QAYEM_LEADS_DB") or None  # unset: lead capture answers that it is unavailable
    leads = LocalDatabase(leads_db) if leads_db else None
    config = settings or Settings.read(lambda name: os.environ.get(name))
    public = SnapshotPublic(catalog)

    async def growth(request: Request) -> Growth:
        return Growth(leads, public, config, http or LocalHttp(), **client_details(request))

    async def load(kind: str, key: str):
        snapshot = catalog.snapshot()
        if kind == "overview":
            return snapshot.overview
        if kind == "article":
            return await editorial.article(Growth(leads, public, config, None), key)
        if kind in ("index", "map", "guide"):
            if kind == "index":
                return snapshot.index if not key else snapshot.editions.get(key)
            return guide_api.map_payload(snapshot) if kind == "map" else guide_api.summary(snapshot)
        return {"compound": snapshot.compounds, "developer": snapshot.developers,
                "district": snapshot.districts}[kind].get(key)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        target = seo.canonical_redirect(str(request.url))
        if target and request.method in {"GET", "HEAD"}:
            return RedirectResponse(target, status_code=301)
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers.setdefault("X-Robots-Tag", "noindex")
        return response

    @app.exception_handler(CatalogUnavailable)
    async def unavailable_handler(request: Request, exc: CatalogUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "5"})

    @app.get("/api/health")
    def health() -> dict:
        catalog.snapshot()
        return {"status": "ok", "database": "available"}

    @app.get("/api/overview")
    def overview() -> dict:
        return catalog.snapshot().overview

    @app.get("/api/catalog")
    def entities() -> dict:
        return catalog.snapshot().catalog

    @app.get("/api/compounds")
    def compounds(
        q: str = Query("", max_length=200),
        district: str = Query("", max_length=200),
        developer: str = Query("", max_length=200),
        sort: Literal["units", "gap_asc", "gap_desc", "opportunities", "name"] = "units",
        page: int = Query(1, ge=1, le=10_000),
        page_size: int = Query(30, ge=1, le=100),
    ) -> dict:
        snapshot = catalog.snapshot()
        items = list(snapshot.compounds.values())
        if q.strip():
            items = [c for c in items if matches(q, c["name"], c["name_ar"], c["district"],
                                                 c["developer"] and c["developer"]["name"],
                                                 c["developer"] and c["developer"]["name_ar"])]
        if district.strip():
            items = [c for c in items if c["district_key"] == slug(district)]
        if developer.strip():
            items = [c for c in items if c["developer"] and c["developer"]["key"] == developer.strip()]
        items = sort_entities(items, sort, RANK_MIN_COMPOUND)
        result = page_of(items, page, page_size)
        result["district"] = snapshot.districts.get(slug(district)) if district.strip() else None
        return result

    @app.get("/api/compounds/{key}")
    async def compound_detail(key: str, request: Request) -> dict:
        snapshot = catalog.snapshot()
        compound = snapshot.compounds.get(key)
        if compound is None:
            raise HTTPException(404, "We have no identified resale listings for this compound.")
        median_ppm = ((compound.get("guide") or {}).get("headline") or {}).get("median_ppm")
        observations = await editorial.compound_observations(await growth(request), compound["key"], median_ppm)
        return {"compound": compound, "district": snapshot.districts.get(compound["district_key"]),
                "developer": snapshot.developers.get(compound["developer"]["key"]) if compound["developer"] else None,
                "observations": observations}

    @app.get("/api/developers")
    def developers(
        q: str = Query("", max_length=200),
        sort: Literal["units", "gap_asc", "gap_desc", "opportunities", "name"] = "units",
        page: int = Query(1, ge=1, le=10_000),
        page_size: int = Query(30, ge=1, le=100),
    ) -> dict:
        items = list(catalog.snapshot().developers.values())
        if q.strip():
            items = [d for d in items if matches(q, d["name"], d["name_ar"], *(c["name"] for c in d["compounds"]),
                                                 *(c["name_ar"] for c in d["compounds"]))]
        return page_of(sort_entities(items, sort, RANK_MIN_DEVELOPER), page, page_size)

    @app.get("/api/developers/{key}")
    def developer_detail(key: str) -> dict:
        developer = catalog.snapshot().developers.get(key)
        if developer is None:
            raise HTTPException(404, "We have no identified resale listings for this developer.")
        return developer

    @app.get("/api/districts/{key}")
    def district_detail(key: str) -> dict:
        district = catalog.snapshot().districts.get(key)
        if district is None:
            raise HTTPException(404, "We have no identified resale listings for this district.")
        return district

    @app.get("/api/guide")
    def price_guide() -> dict:
        return guide_api.summary(catalog.snapshot())

    @app.get("/api/guide/{key}")
    def district_guide(key: str) -> dict:
        entry = guide_api.segments_by_district(catalog.snapshot()).get(key)
        if entry is None:
            raise HTTPException(404, "No published figures for this district yet.")
        return entry

    @app.get("/api/map")
    def map_data() -> dict:
        return guide_api.map_payload(catalog.snapshot())

    @app.get("/api/index")
    def index_latest() -> dict:
        return catalog.snapshot().index

    @app.get("/api/index/{month}")
    def index_month(month: str = PathParam(..., pattern=r"^\d{4}-\d{2}$")) -> dict:
        entry = catalog.snapshot().editions.get(month)
        if entry is None:
            raise HTTPException(404, "No Qayem Index was published for this month.")
        return entry

    @app.get("/data/{name}", include_in_schema=False)
    def index_csv(name: str) -> Response:
        month = seo.csv_month(name)
        snapshot = catalog.snapshot()
        edition = None if month is None else snapshot.index if month == "latest" else snapshot.editions.get(month)
        if edition is None:
            raise HTTPException(404, "No Qayem Index was published for this month.")
        return Response(guide_api.csv_text(edition), media_type="text/csv; charset=utf-8")

    @app.get("/api/evaluate")
    async def evaluate_unit(
        request: Request,
        property_type: str = Query(..., min_length=2, max_length=64),
        area: float = Query(..., ge=20, le=5_000, allow_inf_nan=False),
        price: float = Query(..., ge=100_000, le=1_000_000_000, allow_inf_nan=False),
        compound: str = Query("", max_length=200),
        district: str = Query("", max_length=200),
        down_payment: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        installment_years: float | None = Query(None, gt=0, le=15, allow_inf_nan=False),
        delivery: str = Query("", pattern=r"^(|ready|\d{4}(-\d{2})?)$"),
        finishing: Literal["", "core_shell", "semi_finished", "finished", "furnished"] = "",
    ) -> dict:
        if down_payment is not None and down_payment > price:
            raise HTTPException(422, "The down payment cannot exceed the total price.")
        if not compound.strip() and not district.strip():
            raise HTTPException(422, "Choose the unit's compound or district.")
        result = evaluate(catalog.snapshot(), property_type=property_type, area=area, price=price,
                          compound=compound, district=district, down_payment=down_payment,
                          installment_years=installment_years, delivery=delivery, finishing=finishing)
        await editorial.log_check(await growth(request), result["inputs"], result["status"])
        return result

    @app.get("/api/lookup")
    def lookup(url: str = Query(..., min_length=8, max_length=2048)) -> dict:
        key = url_key(url)
        snapshot = catalog.snapshot()
        record = snapshot.records.get(snapshot.urls.get(key)) if key else None
        if record is None:
            raise HTTPException(404, "We have not indexed that listing link. Enter its details instead.")
        return {"query": evaluate_query(public_unit(record))}

    app.include_router(growth_router(growth))
    app.include_router(editorial.editorial_router(growth))

    @app.api_route("/api", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def unknown_api(path: str = "") -> None:
        raise HTTPException(404, "API endpoint not found.")

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(seo.robots_txt())

    @app.get("/llms.txt", include_in_schema=False)
    def llms() -> PlainTextResponse:
        return PlainTextResponse(seo.llms_txt())

    @app.get("/tiles/{name}", include_in_schema=False)
    def tiles(name: str) -> Response:
        """The basemap archive for local development (in production: the Worker, from R2)."""
        folder = Path(os.environ.get("QAYEM_TILES_DIR", Path(__file__).resolve().parents[2] / ".artifacts" / "map"))
        if name != "egypt.pmtiles" or not (folder / name).is_file():
            raise HTTPException(404, "Not found.")
        return FileResponse(folder / name, media_type="application/octet-stream")

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap() -> Response:
        snapshot = catalog.snapshot()
        minimum = seo.SITEMAP_MIN_UNITS
        districts = sorted({*(d["key"] for d in snapshot.catalog["districts"] if d["units"] >= minimum),
                            *(k for k, d in snapshot.districts.items() if (d.get("guide") or {}).get("headline"))})
        paths = seo.sitemap_paths(
            [k for k, c in snapshot.compounds.items() if c["units"] >= minimum],
            [k for k, d in snapshot.developers.items() if d["units"] >= minimum],
            districts)
        paths += seo.guide_paths(snapshot.overview.get("index_months") or [])
        paths += [p for p, _ in await editorial.article_paths(Growth(leads, public, config, None))]
        return Response(seo.sitemap_xml(paths, snapshot.today), media_type="application/xml")

    if (static_root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def website(request: Request, path: str) -> Response:
        try:
            moved = await seo.retired_redirect("/" + path, dict(request.query_params), public.unit)
        except CatalogUnavailable:  # the listing's guide is unknown for now: send it to the map, not for good
            return RedirectResponse("/map", status_code=302)
        if moved:
            return RedirectResponse(moved, status_code=301)
        requested = (static_root / path).resolve()
        if not requested.is_relative_to(static_root):
            raise HTTPException(404, "Page not found.")
        if requested.is_file() and requested.name != "index.html":
            return FileResponse(requested)
        index = static_root / "index.html"
        if index.is_file() and not Path(path).suffix or requested.name == "index.html":
            html = index.read_text(encoding="utf-8")
            try:
                meta = await seo.page_meta("/" + path, dict(request.query_params), load)
            except Exception:  # the page still loads; the app shows its own retry state
                return Response(html, media_type="text/html")
            return Response(seo.render(html, meta), status_code=meta.status, media_type="text/html")
        if not index.is_file():
            raise HTTPException(503, "Website assets are not built. Run npm install and npm run build in web/, then restart the server.")
        raise HTTPException(404, "Page not found.")

    return app


app = create_app()
