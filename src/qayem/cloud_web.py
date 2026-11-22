"""Async D1 API. Requests read published projections; valuation reuses the local mathematics."""
from __future__ import annotations

from datetime import date
import json
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from . import seo
from .growth import Growth, Settings, WorkerHttp, client_details, growth_router
from .valuation import developer_key, slug
from .web_common import DELIVERY_PATTERN, RANK_MIN_COMPOUND, RANK_MIN_DEVELOPER, Sort, search_query
from .website_data import Snapshot, evaluate, peer_groups, url_key

Level = Literal["", "strong", "good", "in_line", "mixed", "pricier", "check", "unrated"]

def _no_photos(item: dict) -> dict:
    """Sources' photos are never served, even from a catalogue published before they were dropped."""
    if "images" in item:
        item["images"] = []
    if "photo" in item:
        item["photo"] = None
    return item


def public_json(text: str):
    return json.loads(text, object_hook=_no_photos)



class Unavailable(Exception):
    pass


def budget_clauses(*, price_max=None, cash_max=None, signing_max=None, area_min=None, area_max=None,
                   bedrooms_min=None, delivery="", newer_than=None, price_dropped=False) -> tuple[list[str], list]:
    """`web_common.within` in SQL, over each unit's published JSON. NULL never satisfies a limit."""
    cash, remaining = "json_extract(public,'$.payment.cash_equivalent')", "json_extract(public,'$.payment.remaining')"
    rules = [(price_max, "price<=?"), (cash_max, f"{cash}<=?"), (signing_max, f"price-{remaining}<=?"),
             (area_min, "area>=?"), (area_max, "area<=?"), (bedrooms_min, "json_extract(public,'$.bedrooms')>=?"),
             (newer_than, "id>?")]
    clauses = [sql for value, sql in rules if value is not None]
    params = [value for value, _ in rules if value is not None]
    if price_dropped:
        clauses.append("json_extract(public,'$.price_change.change')<0")
    if delivery:
        ready = "json_extract(public,'$.delivery.bucket')='ready'"
        if delivery == "ready":
            clauses.append(ready)
        else:
            clauses.append(f"({ready} OR substr(json_extract(public,'$.delivery.date'),1,4)<=?)")
            params.append(delivery)
    return clauses, params


def _bindable(params):
    """Python None reaches JavaScript as undefined, which D1 rejects; SQL NULL is JavaScript null."""
    try:
        from pyodide.ffi import jsnull
    except ImportError:  # ordinary Python (tests)
        return params
    return [jsnull if value is None else value for value in params]


class D1:
    def __init__(self, binding):
        self.binding = binding

    def _statement(self, sql, params):
        statement = self.binding.prepare(sql)
        return statement.bind(*_bindable(params)) if params else statement

    async def all(self, sql, params=()):
        try:
            result = await self._statement(sql, params).all()
            data = result.to_py() if hasattr(result, "to_py") else result
            if not data.get("success", True):
                raise Unavailable()
            return data["results"]
        except Exception as exc:
            raise Unavailable() from exc

    async def run(self, sql, params=()):
        try:
            result = await self._statement(sql, params).run()
            data = result.to_py() if hasattr(result, "to_py") else result
            if not data.get("success", True):
                raise Unavailable()
            return data.get("meta") or {}
        except Exception as exc:
            raise Unavailable() from exc


UNIT_ORDER = {"opportunity": "opportunity_rank", "launch_gap": "launch_gap,id", "peer_gap": "peer_gap,id",
              "cash_ppm_asc": "cash_ppm,id", "price_asc": "price,id", "price_desc": "price DESC,id",
              "area_desc": "area DESC,id", "newest": "id DESC"}


async def unit_clauses(data, *, q="", district="", compound="", developer="", property_type="", level="", terms="",
                       source="", resale="true", launch="", sort="opportunity", **budget) -> tuple[list[str], list]:
    """The units filter in SQL: the Units API and the nightly alerts select the same units."""
    clauses, params = ["version=?"], [data.version]
    if resale == "true":
        clauses.append("is_default=1")
    for column, value in [("district", slug(district) if district.strip() else ""),
        ("compound", slug(compound) if compound.strip() else ""), ("property_type", property_type.strip().casefold()),
        ("level", level), ("terms", terms), ("source", source.strip().casefold())]:
        if value:
            clauses.append(column + "=?")
            params.append(value)
    if developer.strip():
        key = developer.strip()
        if not await data.document("developer", key):
            key = developer_key(developer)
        clauses.append("developer=?")
        params.append(key)
    if q.strip():
        clauses.append("NOT EXISTS (SELECT 1 FROM json_each(?) term WHERE instr(search,term.value)=0)")
        params.append(json.dumps(search_query(q).split()))
    extra, values = budget_clauses(**budget)
    clauses.extend(extra)
    params.extend(values)
    if launch or sort == "launch_gap":
        clauses.append("launch_gap IS NOT NULL")
    if sort == "launch_gap":
        clauses.extend(["level!='check'", "same_finishing=1"])
    if sort == "peer_gap":
        clauses.extend(["peer_gap IS NOT NULL", "level!='check'"])
    if sort == "cash_ppm_asc":
        clauses.append("cash_ppm IS NOT NULL")
    return clauses, params


class Store:
    def __init__(self, database):
        self.database = database
        self.version = None
        self.today = None

    async def open(self):
        rows = await self.database.all("SELECT d.version,d.today FROM datasets d JOIN state s "
                                       "ON s.value=d.version WHERE s.key='active' AND d.ready=1")
        if not rows:
            raise Unavailable()
        self.version, self.today = rows[0]["version"], date.fromisoformat(rows[0]["today"])
        return self

    async def document(self, kind, key="", required=False):
        rows = await self.database.all("SELECT data FROM documents WHERE version=? AND kind=? AND key=? ORDER BY part",
                                       (self.version, kind, key))
        if required and not rows:
            raise Unavailable()
        return public_json("".join(row["data"] for row in rows)) if rows else None

    async def documents(self, kind):
        rows = await self.database.all("SELECT key,data FROM documents WHERE version=? AND kind=? ORDER BY position,part",
                                       (self.version, kind))
        documents = {}
        for row in rows:
            documents.setdefault(row["key"], []).append(row["data"])
        return [public_json("".join(parts)) for parts in documents.values()]

    async def entities(self, kind, q, sort, page, page_size, district="", developer=""):
        clauses, params = ["version=?", "kind=?"], [self.version, kind]
        if q.strip():
            clauses.append("NOT EXISTS (SELECT 1 FROM json_each(?) term WHERE instr(search,term.value)=0)")
            params.append(json.dumps(search_query(q).split()))
        if district.strip():
            clauses.append("district=?")
            params.append(slug(district))
        if developer.strip():
            clauses.append("developer=?")
            params.append(developer.strip())
        if sort.startswith("gap"):
            clauses.extend(["launch_gap IS NOT NULL", "compared>=?"])
            params.append(RANK_MIN_COMPOUND if kind == "compound" else RANK_MIN_DEVELOPER)
        order = {"units": "position", "name": "name,position", "opportunities": "good_count DESC,units DESC,key",
                 "gap_asc": "launch_gap,position", "gap_desc": "launch_gap DESC,position"}[sort]
        where = " AND ".join(clauses)
        total = (await self.database.all(f"SELECT count(*) AS n FROM entities WHERE {where}", params))[0]["n"]
        selected = (f"SELECT key,row_number() OVER (ORDER BY {order}) AS rank FROM entities WHERE {where} "
                    f"ORDER BY {order} LIMIT ? OFFSET ?")
        rows = await self.database.all("SELECT d.key,d.data FROM documents d JOIN (" + selected + ") selected "
            "ON selected.key=d.key WHERE d.version=? AND d.kind=? ORDER BY selected.rank,d.part",
            (*params, page_size, (page - 1) * page_size, self.version, kind))
        parts = {}
        for row in rows:
            parts.setdefault(row["key"], []).append(row["data"])
        return {"items": [public_json("".join(text)) for text in parts.values()], "total": total,
                "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size}

    async def evaluation_snapshot(self, compound):
        entry = await self.document("compound", slug(compound))
        if entry is None:
            wanted = compound.strip().casefold()
            rows = await self.database.all("SELECT key FROM entities WHERE version=? AND kind='compound' "
                                          "AND (name=? OR name_ar=?) ORDER BY position LIMIT 1",
                                          (self.version, wanted, wanted))
            entry = await self.document("compound", rows[0]["key"]) if rows else None
        records, launches = [], []
        if entry:
            records = await self.database.all("SELECT record FROM units WHERE version=? AND compound=? "
                                              "AND is_default=1 ORDER BY id LIMIT 10001",
                                              (self.version, entry["key"]))
            launches = await self.database.all("SELECT record FROM launches WHERE version=? AND compound=? "
                                               "ORDER BY id LIMIT 10001", (self.version, entry["key"]))
            if len(records) > 10000 or len(launches) > 10000:
                raise Unavailable()  # guard Worker memory without silently reducing comparison evidence
        records = [public_json(row["record"]) for row in records]
        launches = [public_json(row["record"]) for row in launches]
        return Snapshot({r["id"]: r for r in records}, records, self.today,
                        {entry["key"]: entry} if entry else {}, {}, {}, {}, {}, {},
                        {entry["key"]: launches} if entry else {}, peer_groups(records))

    async def load(self, kind, key):
        """A published document for the page head (seo.page_meta)."""
        return await self.document(kind, key)

    async def sitemap(self) -> list[str]:
        async def keys(kind):
            return [row["key"] for row in await self.database.all(
                "SELECT key FROM entities WHERE version=? AND kind=? AND units>=? ORDER BY position",
                (self.version, kind, seo.SITEMAP_MIN_UNITS))]
        compounds, developers = await keys("compound"), await keys("developer")
        catalog = await self.document("catalog", required=True)
        districts = [d["key"] for d in catalog["districts"] if d["units"] >= seo.SITEMAP_MIN_UNITS]
        units = [row["id"] for row in await self.database.all(
            "SELECT id FROM units WHERE version=? AND is_default=1 AND level!='unrated' ORDER BY id", (self.version,))]
        return seo.sitemap_paths(compounds, developers, districts, units)

    async def newest_unit_id(self) -> int:
        rows = await self.database.all("SELECT max(id) AS n FROM units WHERE version=? AND is_default=1", (self.version,))
        return int(rows[0]["n"] or 0) if rows else 0

    async def unit(self, unit_id: int) -> dict | None:
        rows = await self.database.all("SELECT public FROM units WHERE version=? AND id=?", (self.version, unit_id))
        return public_json(rows[0]["public"]) if rows else None


class LazyPublic:
    """The published catalogue for the growth routes, opened only when a route needs it."""

    def __init__(self, database):
        self.database, self._store = database, None

    async def _open(self):
        self._store = self._store or await Store(self.database).open()
        return self._store

    async def newest_unit_id(self):
        return await (await self._open()).newest_unit_id()

    async def unit(self, unit_id):
        return await (await self._open()).unit(unit_id)


_FROM_ENV = object()
_TEMPLATES: dict[str, str] = {}


def _binding(env, name):
    try:
        value = getattr(env, name)
    except Exception:
        return None
    return value if value is not None and "undefined" not in str(type(value)).casefold() else None


def create_cloud_app(database=None, *, leads=_FROM_ENV, http=None, settings=None, template=None):
    app = FastAPI(title="Qayem", docs_url=None, redoc_url=None, openapi_url=None)

    def public_database(request: Request):
        return database if database is not None else D1(request.scope["env"].DB)

    async def store(request: Request):
        return await Store(public_database(request)).open()

    async def growth(request: Request) -> Growth:
        env = request.scope.get("env")
        config = settings or Settings.read(lambda name: getattr(env, name))
        if leads is _FROM_ENV:
            binding = _binding(env, "LEADS_DB") if env is not None else None
            target = D1(binding) if binding is not None else None
        else:
            target = leads
        return Growth(target, LazyPublic(public_database(request)), config, http or WorkerHttp(), **client_details(request))

    async def index_html(request: Request) -> str:
        if template is not None:
            return template
        env = request.scope["env"]
        name = getattr(env, "QAYEM_ENVIRONMENT", "") or "production"
        if name not in _TEMPLATES:  # one fetch per isolate; a deployment starts new isolates
            response = await env.ASSETS.fetch("https://assets.local/")
            _TEMPLATES[name] = await response.text()
        return _TEMPLATES[name]

    def staging(request: Request) -> bool:
        return getattr(request.scope.get("env"), "QAYEM_ENVIRONMENT", "") == "staging"

    @app.exception_handler(Unavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": "Qayem's published catalogue is temporarily unavailable. Please retry."},
                            status_code=503, headers={"Retry-After": "5"})

    @app.middleware("http")
    async def response_headers(request, call_next):
        target = seo.canonical_redirect(str(request.url))
        if target and request.method in {"GET", "HEAD"}:
            return RedirectResponse(target, status_code=301)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        environment = request.scope.get("env")
        if getattr(environment, "QAYEM_ENVIRONMENT", "") == "staging":
            response.headers["X-Qayem-Environment"] = "staging"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
            response.headers.setdefault("X-Robots-Tag", "noindex")
        return response

    @app.get("/api/health")
    async def health(data=Depends(store)):
        return {"status": "ok", "database": "available"}

    @app.get("/api/overview")
    async def overview(data=Depends(store)):
        return await data.document("overview", required=True)

    @app.get("/api/catalog")
    async def catalog(data=Depends(store)):
        return await data.document("catalog", required=True)

    @app.get("/api/units")
    async def units(
        q: str = Query("", max_length=200), district: str = Query("", max_length=200),
        compound: str = Query("", max_length=200), developer: str = Query("", max_length=200),
        property_type: str = Query("", max_length=64), level: Level = "",
        terms: Literal["", "cash", "plan", "partial", "unknown"] = "",
        source: str = Query("", max_length=32), resale: Literal["true", "all"] = "true",
        launch: Literal["", "true"] = "", sort: Sort = "opportunity",
        price_max: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        cash_max: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        signing_max: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        area_min: float | None = Query(None, ge=0, le=100_000, allow_inf_nan=False),
        area_max: float | None = Query(None, ge=0, le=100_000, allow_inf_nan=False),
        bedrooms_min: int | None = Query(None, ge=0, le=12),
        delivery: str = Query("", pattern=DELIVERY_PATTERN), newer_than: int | None = Query(None, ge=0),
        price_dropped: Literal["", "true"] = "",
        page: int = Query(1, ge=1, le=100_000), page_size: int = Query(25, ge=1, le=100),
        data=Depends(store),
    ):
        clauses, params = await unit_clauses(
            data, q=q, district=district, compound=compound, developer=developer, property_type=property_type,
            level=level, terms=terms, source=source, resale=resale, launch=launch, sort=sort, price_max=price_max,
            cash_max=cash_max, signing_max=signing_max, area_min=area_min, area_max=area_max,
            bedrooms_min=bedrooms_min, delivery=delivery, newer_than=newer_than, price_dropped=price_dropped == "true")
        order = UNIT_ORDER[sort]
        where = " AND ".join(clauses)
        total = (await data.database.all(f"SELECT count(*) AS n FROM units WHERE {where}", params))[0]["n"]
        rows = await data.database.all(f"SELECT public FROM units WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                                      (*params, page_size, (page - 1) * page_size))
        return {"items": [public_json(row["public"]) for row in rows], "total": total,
                "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size}

    @app.get("/api/units/{unit_id}")
    async def unit(unit_id: int, data=Depends(store)):
        entry = await data.document("unit_detail", str(unit_id))
        if entry is None:
            raise HTTPException(404, "This unit is unavailable or does not meet the published inclusion rules.")
        if entry["comparables"]:
            ids = [item["id"] for item in entry["comparables"]]
            rows = await data.database.all("SELECT id,public FROM units WHERE version=? AND id IN ("
                                          + ",".join("?" for _ in ids) + ")", (data.version, *ids))
            public = {row["id"]: public_json(row["public"]) for row in rows}
            if len(public) != len(ids):
                raise Unavailable()
            entry["comparables"] = [{**public[item["id"]], "cash_ppm": item["cash_ppm"]}
                                    for item in entry["comparables"]]
        return entry

    @app.get("/api/compounds")
    async def compounds(q: str = Query("", max_length=200), district: str = Query("", max_length=200),
        developer: str = Query("", max_length=200),
        sort: Literal["units", "gap_asc", "gap_desc", "opportunities", "name"] = "units",
        page: int = Query(1, ge=1, le=10_000), page_size: int = Query(30, ge=1, le=100), data=Depends(store)):
        result = await data.entities("compound", q, sort, page, page_size, district, developer)
        result["district"] = await data.document("district", slug(district)) if district.strip() else None
        return result

    @app.get("/api/compounds/{key}")
    async def compound(key: str, data=Depends(store)):
        entry = await data.document("compound", key)
        if entry is None:
            raise HTTPException(404, "We have no identified resale listings for this compound.")
        return {"compound": entry, "district": await data.document("district", entry["district_key"]),
                "developer": await data.document("developer", entry["developer"]["key"]) if entry["developer"] else None}

    @app.get("/api/developers")
    async def developers(q: str = Query("", max_length=200),
        sort: Literal["units", "gap_asc", "gap_desc", "opportunities", "name"] = "units",
        page: int = Query(1, ge=1, le=10_000), page_size: int = Query(30, ge=1, le=100), data=Depends(store)):
        return await data.entities("developer", q, sort, page, page_size)

    @app.get("/api/developers/{key}")
    async def developer(key: str, data=Depends(store)):
        entry = await data.document("developer", key)
        if entry is None:
            raise HTTPException(404, "We have no identified resale listings for this developer.")
        return entry

    @app.get("/api/districts/{key}")
    async def district(key: str, data=Depends(store)):
        entry = await data.document("district", key)
        if entry is None:
            raise HTTPException(404, "We have no identified resale listings for this district.")
        return entry

    @app.get("/api/evaluate")
    async def evaluate_unit(property_type: str = Query(..., min_length=2, max_length=64),
        area: float = Query(..., ge=20, le=5_000, allow_inf_nan=False),
        price: float = Query(..., ge=100_000, le=1_000_000_000, allow_inf_nan=False),
        compound: str = Query(..., min_length=1, max_length=200),
        down_payment: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        installment_years: float | None = Query(None, gt=0, le=15, allow_inf_nan=False),
        delivery: str = Query("", pattern=r"^(|ready|\d{4}(-\d{2})?)$"),
        finishing: Literal["", "core_shell", "semi_finished", "finished", "furnished"] = "", data=Depends(store)):
        if down_payment is not None and down_payment > price:
            raise HTTPException(422, "The down payment cannot exceed the total price.")
        if not compound.strip():
            raise HTTPException(422, "Choose the unit's compound.")
        return evaluate(await data.evaluation_snapshot(compound), property_type=property_type, area=area, price=price,
                        compound=compound, down_payment=down_payment, installment_years=installment_years,
                        delivery=delivery, finishing=finishing)

    @app.get("/api/lookup")
    async def lookup(url: str = Query(..., min_length=8, max_length=2048), data=Depends(store)):
        key = url_key(url)
        rows = await data.database.all("SELECT id FROM units WHERE version=? AND url_key=? LIMIT 2", (data.version, key))
        if len(rows) != 1:
            raise HTTPException(404, "We have not indexed that listing link. Enter its details instead.")
        return {"id": rows[0]["id"]}

    app.include_router(growth_router(growth))

    @app.api_route("/api", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def unknown_api(path: str = ""):
        raise HTTPException(404, "API endpoint not found.")

    @app.get("/robots.txt", include_in_schema=False)
    async def robots(request: Request):
        return PlainTextResponse(seo.robots_txt(staging(request)), headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/llms.txt", include_in_schema=False)
    async def llms(request: Request):
        if staging(request):
            raise HTTPException(404, "Not found.")
        return PlainTextResponse(seo.llms_txt(), headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/sitemap.xml", include_in_schema=False)
    async def sitemap(data=Depends(store)):
        return Response(seo.sitemap_xml(await data.sitemap(), data.today), media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/{path:path}", include_in_schema=False)
    async def page(request: Request, path: str = ""):
        """The single-page app's index.html with this route's head and summary (see seo.py)."""
        if "." in path.rsplit("/", 1)[-1]:
            raise HTTPException(404, "Page not found.")
        html = await index_html(request)
        try:
            data = await store(request)
            meta = await seo.page_meta("/" + path, dict(request.query_params), data.load)
        except Exception as exc:  # never let the head fail the page: the app shows its own retry state
            if not isinstance(exc, Unavailable):
                print("Page head failed:", type(exc).__name__, path[:120])
            return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})
        return Response(seo.render(html, meta, staging=staging(request)), status_code=meta.status,
                        media_type="text/html", headers={"Cache-Control": "no-cache"})

    return app
