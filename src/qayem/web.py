"""FastAPI application serving the Qayem read-only website and JSON API."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from threading import Thread
from typing import Collection, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import crawled_sources, db_path as configured_db_path
from .valuation import developer_key, slug
from .website_data import Catalog, CatalogUnavailable, detail, evaluate, opportunity_key, public_unit, url_key

from .web_common import DELIVERY_PATTERN, RANK_MIN_COMPOUND, RANK_MIN_DEVELOPER, Sort, matches, page_of, sort_entities, within

Level = Literal["", "strong", "good", "in_line", "mixed", "pricier", "check", "unrated"]


_CONFIGURED = object()


def create_app(db_path: str | Path | None = None, static_dir: str | Path | None = None,
               refresh_seconds: float | None = None, sources: Collection[str] | None | object = _CONFIGURED) -> FastAPI:
    if refresh_seconds is None:
        refresh_seconds = float(os.environ.get("QAYEM_REFRESH_SECONDS", "300"))
    if sources is _CONFIGURED:
        sources = crawled_sources()  # benchmark rows are read for launch prices, never listed
    catalog = Catalog(db_path if db_path is not None else configured_db_path(), refresh_seconds, sources)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Thread(target=catalog.warm, name="qayem-catalog-warm", daemon=True).start()  # the first fit takes seconds
        yield

    app = FastAPI(title="Qayem Market Evaluation", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.catalog = catalog
    static_root = Path(static_dir) if static_dir is not None else Path(__file__).resolve().parents[2] / "web" / "dist"
    static_root = static_root.resolve()

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

    @app.get("/api/units")
    def units(
        q: str = Query("", max_length=200),
        district: str = Query("", max_length=200),
        compound: str = Query("", max_length=200),
        developer: str = Query("", max_length=200),
        property_type: str = Query("", max_length=64),
        level: Level = "",
        terms: Literal["", "cash", "plan", "partial", "unknown"] = "",
        source: str = Query("", max_length=32),
        resale: Literal["true", "all"] = "true",
        launch: Literal["", "true"] = "",
        sort: Sort = "opportunity",
        price_max: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        cash_max: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        signing_max: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        area_min: float | None = Query(None, ge=0, le=100_000, allow_inf_nan=False),
        area_max: float | None = Query(None, ge=0, le=100_000, allow_inf_nan=False),
        bedrooms_min: int | None = Query(None, ge=0, le=12),
        delivery: str = Query("", pattern=DELIVERY_PATTERN),
        newer_than: int | None = Query(None, ge=0),
        page: int = Query(1, ge=1, le=100_000),
        page_size: int = Query(25, ge=1, le=100),
    ) -> dict:
        snapshot = catalog.snapshot()
        items = list(snapshot.default if resale == "true" else snapshot.records.values())
        if q.strip():
            items = [r for r in items if matches(q, r["title"], r["district"], r["compound_name"], r["developer_name"],
                                                 r["compound"] and r["compound"]["name"],
                                                 r["compound"] and r["compound"]["name_ar"],
                                                 r["developer"] and r["developer"]["name"],
                                                 r["developer"] and r["developer"]["name_ar"])]
        if district.strip():
            items = [r for r in items if slug(r["district"]) == slug(district)]
        if compound.strip():
            items = [r for r in items if r["compound_key"] == slug(compound)]
        if developer.strip():
            key = developer.strip() if developer.strip() in snapshot.developers else developer_key(developer)
            items = [r for r in items if r["developer_key"] == key]
        if property_type.strip():
            items = [r for r in items if r["property_type"] == property_type.strip().casefold()]
        if level:
            items = [r for r in items if r["opportunity"]["level"] == level]
        if terms:
            items = [r for r in items if r["payment"]["terms"] == terms]
        if source.strip():
            items = [r for r in items if r["source"] == source.strip().casefold()]
        if launch or sort == "launch_gap":  # only units with a current developer price for a similar unit
            items = [r for r in items if r.get("launch")]
        budget = {"price_max": price_max, "cash_max": cash_max, "signing_max": signing_max, "area_min": area_min,
                  "area_max": area_max, "bedrooms_min": bedrooms_min, "delivery": delivery, "newer_than": newer_than}
        if any(value not in (None, "") for value in budget.values()):
            items = [r for r in items if within(r, **budget)]
        if sort == "opportunity":
            items.sort(key=opportunity_key)
        elif sort == "launch_gap":  # like for like only: a listing error or an unfinished unit is not a deal
            items = [r for r in items if r["opportunity"]["level"] != "check" and r["launch"]["same_finishing"]]
            items.sort(key=lambda r: (r["launch"]["gap"], r["id"]))
        elif sort == "peer_gap":
            items = [r for r in items if r["peers"] and r["opportunity"]["level"] != "check"]
            items.sort(key=lambda r: (r["peers"]["gap"], r["id"]))
        elif sort == "cash_ppm_asc":
            items = [r for r in items if r["payment"]["cash_equivalent"]]
            items.sort(key=lambda r: (r["payment"]["cash_equivalent"] / r["area_m2"], r["id"]))
        elif sort == "newest":
            items.sort(key=lambda r: -r["id"])
        else:
            key = {"price_asc": "price", "price_desc": "price", "area_desc": "area_m2"}[sort]
            direction = -1 if sort in {"price_desc", "area_desc"} else 1
            items.sort(key=lambda r: (direction * r[key], r["id"]))
        result = page_of(items, page, page_size)
        result["items"] = [public_unit(r) for r in result["items"]]
        return result

    @app.get("/api/units/{unit_id}")
    def unit_detail(unit_id: int) -> dict:
        snapshot = catalog.snapshot()
        record = snapshot.records.get(unit_id)
        if record is None:
            raise HTTPException(404, "This unit is unavailable or does not meet the published inclusion rules.")
        return detail(snapshot, record, catalog.description(unit_id))

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
    def compound_detail(key: str) -> dict:
        snapshot = catalog.snapshot()
        compound = snapshot.compounds.get(key)
        if compound is None:
            raise HTTPException(404, "We have no identified resale listings for this compound.")
        return {"compound": compound, "district": snapshot.districts.get(compound["district_key"]),
                "developer": snapshot.developers.get(compound["developer"]["key"]) if compound["developer"] else None}

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

    @app.get("/api/evaluate")
    def evaluate_unit(
        property_type: str = Query(..., min_length=2, max_length=64),
        area: float = Query(..., ge=20, le=5_000, allow_inf_nan=False),
        price: float = Query(..., ge=100_000, le=1_000_000_000, allow_inf_nan=False),
        compound: str = Query(..., min_length=1, max_length=200),
        down_payment: float | None = Query(None, ge=0, le=1_000_000_000, allow_inf_nan=False),
        installment_years: float | None = Query(None, gt=0, le=15, allow_inf_nan=False),
        delivery: str = Query("", pattern=r"^(|ready|\d{4}(-\d{2})?)$"),
        finishing: Literal["", "core_shell", "semi_finished", "finished", "furnished"] = "",
    ) -> dict:
        if down_payment is not None and down_payment > price:
            raise HTTPException(422, "The down payment cannot exceed the total price.")
        if not compound.strip():
            raise HTTPException(422, "Choose the unit's compound.")
        return evaluate(catalog.snapshot(), property_type=property_type, area=area, price=price,
                        compound=compound, down_payment=down_payment, installment_years=installment_years,
                        delivery=delivery, finishing=finishing)

    @app.get("/api/lookup")
    def lookup(url: str = Query(..., min_length=8, max_length=2048)) -> dict:
        key = url_key(url)
        unit_id = catalog.snapshot().urls.get(key) if key else None
        if unit_id is None:
            raise HTTPException(404, "We have not indexed that listing link. Enter its details instead.")
        return {"id": unit_id}

    @app.api_route("/api", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def unknown_api(path: str = "") -> None:
        raise HTTPException(404, "API endpoint not found.")

    if (static_root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static_root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def website(path: str) -> FileResponse:
        requested = (static_root / path).resolve()
        if not requested.is_relative_to(static_root):
            raise HTTPException(404, "Page not found.")
        if requested.is_file():
            return FileResponse(requested)
        index = static_root / "index.html"
        if index.is_file() and not Path(path).suffix:
            return FileResponse(index, media_type="text/html")
        if not index.is_file():
            raise HTTPException(503, "Website assets are not built. Run npm install and npm run build in web/, then restart the server.")
        raise HTTPException(404, "Page not found.")

    return app


app = create_app()
