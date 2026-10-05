"""Async D1 API. Requests read published projections; valuation reuses the local mathematics."""
from __future__ import annotations

from datetime import date
import json
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .valuation import developer_key, slug
from .web_common import RANK_MIN_COMPOUND, RANK_MIN_DEVELOPER, search_query
from .website_data import Snapshot, evaluate, peer_groups, url_key

Level = Literal["", "strong", "good", "in_line", "mixed", "pricier", "check", "unrated"]


class Unavailable(Exception):
    pass


class D1:
    def __init__(self, binding):
        self.binding = binding

    async def all(self, sql, params=()):
        try:
            statement = self.binding.prepare(sql)
            if params:
                statement = statement.bind(*params)
            result = await statement.all()
            data = result.to_py() if hasattr(result, "to_py") else result
            if not data.get("success", True):
                raise Unavailable()
            return data["results"]
        except Exception as exc:
            raise Unavailable() from exc


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
        return json.loads("".join(row["data"] for row in rows)) if rows else None

    async def documents(self, kind):
        rows = await self.database.all("SELECT key,data FROM documents WHERE version=? AND kind=? ORDER BY position,part",
                                       (self.version, kind))
        documents = {}
        for row in rows:
            documents.setdefault(row["key"], []).append(row["data"])
        return [json.loads("".join(parts)) for parts in documents.values()]

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
        return {"items": [json.loads("".join(text)) for text in parts.values()], "total": total,
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
        records = [json.loads(row["record"]) for row in records]
        launches = [json.loads(row["record"]) for row in launches]
        return Snapshot({r["id"]: r for r in records}, records, self.today,
                        {entry["key"]: entry} if entry else {}, {}, {}, {}, {}, {},
                        {entry["key"]: launches} if entry else {}, peer_groups(records))


def create_cloud_app(database=None):
    app = FastAPI(title="Qayem", docs_url=None, redoc_url=None, openapi_url=None)

    async def store(request: Request):
        return await Store(database if database is not None else D1(request.scope["env"].DB)).open()

    @app.exception_handler(Unavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": "Qayem's published catalogue is temporarily unavailable. Please retry."},
                            status_code=503, headers={"Retry-After": "5"})

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        environment = request.scope.get("env")
        if getattr(environment, "QAYEM_ENVIRONMENT", "") == "staging":
            response.headers["X-Qayem-Environment"] = "staging"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
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
        launch: Literal["", "true"] = "",
        sort: Literal["opportunity", "launch_gap", "peer_gap", "price_asc", "price_desc", "area_desc",
                      "cash_ppm_asc"] = "opportunity",
        page: int = Query(1, ge=1, le=100_000), page_size: int = Query(25, ge=1, le=100),
        data=Depends(store),
    ):
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
        order = {"opportunity": "opportunity_rank", "launch_gap": "launch_gap,id", "peer_gap": "peer_gap,id",
                 "cash_ppm_asc": "cash_ppm,id", "price_asc": "price,id", "price_desc": "price DESC,id",
                 "area_desc": "area DESC,id"}[sort]
        if launch or sort == "launch_gap":
            clauses.append("launch_gap IS NOT NULL")
        if sort == "launch_gap":
            clauses.extend(["level!='check'", "same_finishing=1"])
        if sort == "peer_gap":
            clauses.extend(["peer_gap IS NOT NULL", "level!='check'"])
        if sort == "cash_ppm_asc":
            clauses.append("cash_ppm IS NOT NULL")
        where = " AND ".join(clauses)
        total = (await data.database.all(f"SELECT count(*) AS n FROM units WHERE {where}", params))[0]["n"]
        rows = await data.database.all(f"SELECT public FROM units WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                                      (*params, page_size, (page - 1) * page_size))
        return {"items": [json.loads(row["public"]) for row in rows], "total": total,
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
            public = {row["id"]: json.loads(row["public"]) for row in rows}
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

    @app.api_route("/api", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def unknown_api(path: str = ""):
        raise HTTPException(404, "API endpoint not found.")

    return app
