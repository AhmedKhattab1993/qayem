"""Server-rendered head tags, crawlable page summaries, sitemap and robots for the public site.

The website is a single-page app, so without this every URL shares one generic title and a
shared link shows no numbers. Each public route gets an Arabic title and description built from
the same published documents the API serves, a canonical URL on the apex host, Open Graph and
Twitter tags (WhatsApp previews), JSON-LD, and a short static summary inside the app's root
element that crawlers read and React replaces on load. Nothing here runs a comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html import escape
import json
import re
from typing import Awaitable, Callable
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit, urlunsplit

SITE = "https://qayem.ai"
CANONICAL_HOST = "qayem.ai"
REDIRECT_HOSTS = {"www.qayem.ai"}
DEFAULT_IMAGE = "/og-default.png"
BRAND = "قيّم"

TYPE_AR = {
    "apartment": "شقة", "villa": "فيلا", "chalet": "شاليه", "townhouse": "تاون هاوس", "twinhouse": "توين هاوس",
    "penthouse": "بنتهاوس", "duplex": "دوبلكس", "studio": "استوديو", "office": "مكتب", "shop": "محل",
    "clinic": "عيادة", "cabin": "كابينة", "loft": "لوفت", "land": "أرض", "family house": "بيت عائلة",
}
CLASS_AR = {"apartment": "الشقق", "chalet": "الشاليهات", "house": "الفيلات والمنازل"}
LEVEL_AR = {
    "strong": "فرصة قوية", "good": "فرصة جيدة", "in_line": "في المتوسط", "mixed": "إشارات متعارضة",
    "pricier": "أغلى من البدائل", "check": "راجع هذا الإعلان", "unrated": "لا يكفي للمقارنة",
}
# The website's own district names in Arabic (web/src/lib.ts keeps the same list for the interface).
DISTRICT_AR = {
    "New Cairo": "القاهرة الجديدة", "New Capital City": "العاصمة الإدارية الجديدة", "North Coast": "الساحل الشمالي",
    "6th of October City": "مدينة ٦ أكتوبر", "Mostakbal City": "مدينة المستقبل", "Ras El Hekma": "رأس الحكمة",
    "New Zayed": "زايد الجديدة", "Madinaty": "مدينتي", "El Sheikh Zayed": "الشيخ زايد", "Al Alamein": "العلمين",
    "October Gardens": "حدائق أكتوبر", "Ain Sokhna": "العين السخنة", "El Shorouk": "الشروق", "Nasr City": "مدينة نصر",
    "6th settlement": "التجمع السادس", "New Heliopolis": "هليوبوليس الجديدة", "Alexandria": "الإسكندرية",
    "Maadi": "المعادي", "Northern Expansion": "التوسعات الشمالية", "Ras Sudr": "رأس سدر", "Makadi": "مكادي",
    "Sidi Abdel Rahman": "سيدي عبد الرحمن", "Borg el arab": "برج العرب", "Al Dabaa": "الضبعة",
}
# Pages people keep for themselves; nothing for a search engine to index.
PRIVATE = ("/compare", "/watchlist", "/sheet/")


@dataclass
class Meta:
    title: str
    description: str
    path: str
    image: str = DEFAULT_IMAGE
    kind: str = "website"
    index: bool = True
    status: int = 200
    jsonld: list[dict] = field(default_factory=list)
    body: str = ""


Loader = Callable[[str, str], Awaitable[dict | None]]


# --- small Arabic formatters ------------------------------------------------------------

def place_ar(name: str | None) -> str:
    return DISTRICT_AR.get(name or "", name or "")


def name_ar(entity: dict | None) -> str:
    if not entity:
        return ""
    return entity.get("name_ar") or entity.get("name") or ""


def both_names(entity: dict | None) -> str:
    """«باديا (Badya)»: the Arabic name people search with, and the Latin one listings use."""
    if not entity:
        return ""
    arabic, latin = entity.get("name_ar"), entity.get("name") or ""
    return f"{arabic} ({latin})" if arabic and arabic.casefold() != latin.casefold() else latin


def type_ar(kind: str | None) -> str:
    return TYPE_AR.get((kind or "").casefold(), kind or "وحدة")


def money_ar(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + " مليون جنيه"
    return f"{round(value / 1000):,} ألف جنيه"


def ppm_ar(value: float | None) -> str:
    return "—" if value is None else f"{round(value, -2):,.0f} جنيه للمتر"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{abs(round(value * 100))}%"


def gap_ar(value: float | None, against: str) -> str:
    """«أرخص 12% من المطور اليوم» / «أغلى 8% من …» / «بنفس سعر …»."""
    if value is None:
        return ""
    if abs(value) < 0.005:
        return f"بنفس سعر {against}"
    return f"{'أرخص' if value < 0 else 'أغلى'} {pct(value)} من {against}"


def _primary_class(classes: list[dict]) -> dict | None:
    return max(classes, key=lambda c: c["units"]) if classes else None


# --- FAQ: questions people ask, answered from the live numbers -------------------------

def compound_faq(compound: dict) -> list[tuple[str, str]]:
    name = name_ar(compound)
    developer = name_ar(compound.get("developer")) or "المطور"
    items: list[tuple[str, str]] = []
    main = _primary_class(compound.get("classes") or [])
    if main and main.get("median_asking_ppm"):
        cash = f"، أي {ppm_ar(main['median_cash_ppm'])} بقيمة اليوم بعد خصم الأقساط" if main.get("median_cash_ppm") else ""
        items.append((f"ما متوسط سعر المتر ريسيل في {name}؟",
                      f"متوسط سعر عقد المتر في {CLASS_AR.get(main['class'], 'الوحدات')} الريسيل في {name} "
                      f"{ppm_ar(main['median_asking_ppm'])}{cash}، من {main['units']} إعلان معروض الآن."))
    launch = compound.get("launch")
    if launch and launch.get("median_gap") is not None:
        items.append((f"هل الريسيل في {name} أرخص من سعر {developer} اليوم؟",
                      f"الوحدة الريسيل النموذجية في {name} {gap_ar(launch['median_gap'], 'وحدة مماثلة يبيعها ' + developer + ' اليوم')}، "
                      f"على الأقل تفضيلًا بين السعر المعلن وقيمته اليوم، عبر {launch['compared']} وحدة بنفس النوع والتشطيب والمساحة."))
    opportunities = compound.get("opportunities") or {}
    rated = sum(count for level, count in opportunities.items() if level != "unrated")
    if rated:
        items.append((f"كم فرصة ريسيل حقيقية في {name} الآن؟",
                      f"{compound.get('good_count', 0)} من {rated} وحدة مُقارنة أرخص بوضوح من البدائل المتاحة اليوم "
                      f"(سعر المطور والوحدات المماثلة المعروضة)."))
    history = compound.get("history") or {}
    if history.get("delisted_30d") is not None and compound.get("units"):
        speed = (f" ومتوسط بقاء الوحدة المعروضة حديثًا {history['median_days_listed']} يومًا قبل خروجها"
                 if history.get("median_days_listed") is not None else "")
        items.append((f"ما سرعة بيع الوحدات في {name}؟",
                      f"خرج {history['delisted_30d']} إعلان من سوق الريسيل في {name} خلال آخر 30 يومًا "
                      f"({pct(history.get('turnover_30d'))} من المعروض){speed}. الخروج قد يعني البيع أو سحب الإعلان."))
    if compound.get("ready_share") is not None:
        wait = (f"، وتُسلَّم البقية بعد {compound['median_years_to_delivery']} سنة في المتوسط"
                if compound.get("median_years_to_delivery") else "")
        items.append((f"هل وحدات الريسيل في {name} استلام فوري؟",
                      f"{pct(compound['ready_share'])} من وحدات الريسيل المعروضة في {name} جاهزة للاستلام{wait}."))
    return items


def district_faq(district: dict) -> list[tuple[str, str]]:
    name = place_ar(district.get("name"))
    items: list[tuple[str, str]] = []
    main = _primary_class(district.get("classes") or [])
    if main and main.get("median_asking_ppm"):
        items.append((f"ما متوسط سعر المتر ريسيل في {name}؟",
                      f"متوسط سعر عقد المتر في {CLASS_AR.get(main['class'], 'الوحدات')} الريسيل في {name} "
                      f"{ppm_ar(main['median_asking_ppm'])}، من {main['units']} إعلان في {district.get('compound_count', 0)} كمبوند."))
    below = [c for c in district.get("compounds") or [] if c.get("median_gap") is not None]
    if below:
        best = sorted(below, key=lambda c: c["median_gap"])[:3]
        listed = "، ".join(f"{name_ar(c)} ({gap_ar(c['median_gap'], 'المطور')})" for c in best)
        items.append((f"ما أرخص كمبوندات {name} ريسيل مقارنة بسعر المطور؟", f"الأبعد تحت سعر المطور اليوم: {listed}."))
    opportunities = district.get("opportunities") or {}
    good = opportunities.get("strong", 0) + opportunities.get("good", 0)
    rated = sum(count for level, count in opportunities.items() if level != "unrated")
    if rated:
        items.append((f"كم فرصة ريسيل في {name} الآن؟",
                      f"{good} من {rated} وحدة مُقارنة في {name} أرخص بوضوح من سعر المطور والوحدات المماثلة."))
    history = district.get("history") or {}
    if history.get("delisted_30d") is not None:
        items.append((f"ما سرعة بيع وحدات الريسيل في {name}؟",
                      f"خرج {history['delisted_30d']} إعلان خلال آخر 30 يومًا ({pct(history.get('turnover_30d'))} من المعروض)."))
    return items


def faq_jsonld(items: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}


def breadcrumbs(*crumbs: tuple[str, str]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": SITE + path} for i, (name, path) in enumerate(crumbs)]}


# --- static summaries (crawlers read these; React replaces them on load) --------------

def _summary(heading: str, lead: str, facts: list[str] = (), faq: list[tuple[str, str]] = (),
             links: list[tuple[str, str]] = ()) -> str:
    parts = [f"<h1>{escape(heading)}</h1>", f"<p>{escape(lead)}</p>"]
    if facts:
        parts.append("<ul>" + "".join(f"<li>{escape(f)}</li>" for f in facts if f) + "</ul>")
    if faq:
        parts.append("<h2>أسئلة شائعة</h2>" + "".join(f"<h3>{escape(q)}</h3><p>{escape(a)}</p>" for q, a in faq))
    if links:
        parts.append("<nav>" + " · ".join(f'<a href="{escape(path)}">{escape(label)}</a>' for label, path in links) + "</nav>")
    return '<div class="seo-summary">' + "".join(parts) + "</div>"


NAV = [("قارن وحدة", "/evaluate"), ("الكمبوندات", "/compounds"), ("المطورون", "/developers"),
       ("المناطق", "/districts"), ("الوحدات", "/units"), ("المنهجية", "/methodology")]


# --- per-route meta --------------------------------------------------------------------

def home_meta(overview: dict | None) -> Meta:
    title = f"{BRAND} — هل سعر الوحدة الريسيل لقطة فعلًا؟ مقارنة بسعر المطور اليوم"
    if overview:
        good = (overview.get("opportunities") or {}).get("strong", 0) + (overview.get("opportunities") or {}).get("good", 0)
        description = (f"قيّم يقارن {overview['total_resale']:,} وحدة ريسيل في {overview['compound_count']} كمبوند "
                       f"بسعر المطور اليوم وبالوحدات المماثلة المعروضة، كاش وبقيمة الأقساط اليوم. "
                       f"{good:,} فرصة قوية أو جيدة الآن.")
    else:
        description = "قيّم يقارن كل وحدة ريسيل في مصر بسعر المطور اليوم وبالوحدات المماثلة المعروضة، كاش وبقيمة الأقساط اليوم."
    site = {"@context": "https://schema.org", "@type": "WebSite", "name": BRAND, "alternateName": "Qayem", "url": SITE + "/",
            "inLanguage": ["ar", "en"], "potentialAction": {"@type": "SearchAction",
            "target": SITE + "/units?q={search_term_string}", "query-input": "required name=search_term_string"}}
    organization = {"@context": "https://schema.org", "@type": "Organization", "name": "Qayem", "url": SITE + "/",
                    "logo": SITE + "/favicon.svg"}
    return Meta(title, description, "/", jsonld=[site, organization],
                body=_summary("هل هي فرصة حقيقية؟", description, links=NAV))


STATIC = {
    "/evaluate": ("حاسبة تقييم سعر وحدة ريسيل في مصر — كاش وتقسيط مقابل سعر المطور | قيّم",
                  "صِف الوحدة المعروضة عليك: يحوّل قيّم خطة السداد إلى قيمتها اليوم ويقارنها بسعر المطور اليوم وبالوحدات المماثلة في الكمبوند نفسه."),
    "/units": ("وحدات ريسيل للبيع في مصر مقارنة بسعر المطور — الأفضل أولًا | قيّم",
               "كل وحدة ريسيل مقارنة بسعر المطور اليوم وبالوحدات المماثلة في كمبوندها، مع فلاتر الميزانية والكاش والمقدم والتسليم."),
    "/compounds": ("أسعار الكمبوندات في مصر — الريسيل مقابل سعر المطور اليوم | قيّم",
                   "متوسط سعر المتر ريسيل وسعر المطور اليوم والفرص في كل كمبوند، في القاهرة الجديدة وأكتوبر والساحل والعاصمة وغيرها."),
    "/developers": ("المطورون العقاريون في مصر — أسعار الريسيل مقابل أسعارهم الجديدة | قيّم",
                    "كيف تقارن وحدات الريسيل في مشروعات كل مطور بأسعاره الجديدة اليوم، كمبوندًا كمبوندًا."),
    "/districts": ("مناطق العقارات في مصر — أسعار الريسيل مقابل المطور | قيّم",
                   "أسعار المتر ريسيل وسعر المطور اليوم وعدد الفرص في كل منطقة: القاهرة الجديدة، ٦ أكتوبر، الساحل الشمالي، المستقبل، العاصمة الإدارية."),
    "/methodology": ("كيف يقارن قيّم وحدات الريسيل بسعر المطور — المنهجية | قيّم",
                     "مقارنتان لكل وحدة: بسعر المطور اليوم لوحدة مماثلة، وبالوحدات المماثلة المعروضة الآن، كاش وبقيمة الأقساط اليوم. لا يوجد سعر عادل."),
    "/privacy": ("الخصوصية — ماذا يحفظ قيّم ولماذا | قيّم",
                 "ما الذي يحفظه قيّم عند طلب تنبيه أو عرض، ولماذا، وكيف تلغي. لن نشارك رقمك مع سماسرة بدون إذنك."),
}


def evaluate_meta(query: dict[str, str]) -> Meta:
    title, description = STATIC["/evaluate"]
    compound, kind, area, price = (query.get(k, "").strip() for k in ("compound", "property_type", "area", "price"))
    if query.get("mode") == "sell":
        title = "بِع وحدتك الريسيل: كيف يقارن المشترون سعرك؟ — تقييم مجاني | قيّم"
        description = "قبل أن تعرض وحدتك: شاهد كيف يقارنها المشترون بسعر المطور اليوم وبالوحدات المماثلة في كمبوندك، واعرف متى يبحث مشترون في كمبوندك."
    elif compound and area and price:
        try:
            title = (f"هل {type_ar(kind)} {float(area):,.0f} م² في {compound[:60]} بسعر {money_ar(float(price))} لقطة؟ | قيّم")
        except ValueError:
            pass
    return Meta(title, description, "/evaluate", body=_summary("هل هي فرصة حقيقية؟", description, links=NAV))


def unit_meta(detail: dict | None, unit_id: str) -> Meta:
    if not detail:
        return not_found(f"/units/{unit_id}")
    unit = detail["unit"]
    compound = unit.get("compound")
    where = name_ar(compound) or place_ar(unit.get("district"))
    beds = f" {unit['bedrooms']} غرف" if unit.get("bedrooms") else ""
    name = f"{type_ar(unit['property_type'])} {unit['area_m2']:,.0f} م²{beds}"
    launch, peers, level = unit.get("launch"), unit.get("peers"), unit["opportunity"]["level"]
    headline = (gap_ar(launch["gap"], "المطور") if launch and launch.get("same_finishing")
                else gap_ar(peers["gap"], "المماثل") if peers else LEVEL_AR[level])
    title = f"{name} في {where} — {headline} | قيّم"
    payment = unit["payment"]
    terms = (f"تقسيط {payment['years']:g} سنة" if payment["terms"] == "plan" and payment.get("years")
             else "كاش" if payment["terms"] == "cash" else "طريقة السداد غير منشورة")
    parts = [f"{money_ar(unit['price'])} ({terms})"]
    if payment.get("cash_equivalent") and payment["terms"] == "plan":
        parts.append(f"قيمتها اليوم {money_ar(payment['cash_equivalent'])}")
    if launch and launch.get("same_finishing"):
        parts.append(gap_ar(launch["gap"], "سعر المطور اليوم"))
    if peers:
        parts.append(f"{gap_ar(peers['gap'], 'الوحدات المماثلة')} (ترتيبها {peers['rank']} من {peers['count']})")
    parts.append(f"التقييم: {LEVEL_AR[level]}")
    description = " • ".join(parts) + f". {place_ar(unit.get('district'))}."
    image = next((url for url in unit.get("images") or [] if url.startswith("https://")), DEFAULT_IMAGE)
    crumbs = [("قيّم", "/")]
    if compound:
        crumbs.append((name_ar(compound), f"/compounds/{quote(compound['key'])}"))
    crumbs.append((name, f"/units/{unit['id']}"))
    listing = {"@context": "https://schema.org", "@type": "RealEstateListing", "name": f"{name} — {where}",
               "url": f"{SITE}/units/{unit['id']}", "description": description,
               "offers": {"@type": "Offer", "price": round(unit["price"]), "priceCurrency": "EGP"}}
    if image != DEFAULT_IMAGE:
        listing["image"] = image
    links = [(name_ar(compound), f"/compounds/{quote(compound['key'])}")] if compound else []
    if unit.get("developer"):
        links.append((name_ar(unit["developer"]), f"/developers/{quote(unit['developer']['key'])}"))
    links.append(("قارن وحدة أخرى", "/evaluate"))
    return Meta(title, description, f"/units/{unit['id']}", image=image, kind="article",
                jsonld=[listing, breadcrumbs(*crumbs)], body=_summary(f"{name} في {where}", description, links=links))


def compound_meta(compound: dict | None, key: str) -> Meta:
    if not compound:
        return not_found(f"/compounds/{quote(key)}")
    name, developer = name_ar(compound), name_ar(compound.get("developer"))
    title = f"أسعار ريسيل {both_names(compound)} اليوم — مقارنة بسعر {developer or 'المطور'} | قيّم"
    main = _primary_class(compound.get("classes") or [])
    parts = [f"{compound['units']} وحدة ريسيل في {name} ب{place_ar(compound.get('district'))}"]
    if main and main.get("median_asking_ppm"):
        parts.append(f"متوسط سعر المتر ريسيل {ppm_ar(main['median_asking_ppm'])}"
                     + (f" مقابل {ppm_ar(main['developer_ppm'])} عند المطور اليوم" if main.get("developer_ppm") else ""))
    launch = compound.get("launch")
    if launch and launch.get("median_gap") is not None:
        parts.append(f"الريسيل {gap_ar(launch['median_gap'], 'المطور')}")
    parts.append(f"{compound.get('good_count', 0)} فرصة قوية أو جيدة")
    description = "، ".join(parts) + "."
    faq = compound_faq(compound)
    path = f"/compounds/{quote(compound['key'])}"
    crumbs = [("قيّم", "/"), ("الكمبوندات", "/compounds")]
    if compound.get("district_key"):
        crumbs.append((place_ar(compound.get("district")), f"/districts/{quote(compound['district_key'])}"))
    crumbs.append((name, path))
    links = [(f"وحدات {name}", f"/units?compound={quote(compound['key'])}"),
             (f"قيّم وحدة في {name}", f"/evaluate?compound={quote(compound['name'])}")]
    if compound.get("developer"):
        links.append((developer, f"/developers/{quote(compound['developer']['key'])}"))
    if compound.get("district_key"):
        links.append((place_ar(compound.get("district")), f"/districts/{quote(compound['district_key'])}"))
    jsonld = [breadcrumbs(*crumbs)] + ([faq_jsonld(faq)] if faq else [])
    return Meta(title, description, path, jsonld=jsonld,
                body=_summary(f"أسعار ريسيل {both_names(compound)}", description, faq=faq, links=links))


def developer_meta(developer: dict | None, key: str) -> Meta:
    if not developer:
        return not_found(f"/developers/{quote(key)}")
    name = name_ar(developer)
    title = f"أسعار ريسيل مشروعات {both_names(developer)} مقابل أسعارها الجديدة اليوم | قيّم"
    parts = [f"{developer['units']} وحدة ريسيل في {len(developer.get('compounds') or [])} كمبوند لـ{name}"]
    launch = developer.get("launch")
    if launch and launch.get("median_gap") is not None:
        parts.append(f"الريسيل {gap_ar(launch['median_gap'], 'أسعار ' + name + ' اليوم')}")
    parts.append(f"{developer.get('good_count', 0)} فرصة قوية أو جيدة")
    description = "، ".join(parts) + "."
    path = f"/developers/{quote(developer['key'])}"
    compounds = developer.get("compounds") or []
    facts = [f"{name_ar(c)}: {c['units']} وحدة" + (f"، {gap_ar(c['median_gap'], 'المطور')}" if c.get("median_gap") is not None else "")
             for c in compounds[:12]]
    links = [(name_ar(c), f"/compounds/{quote(c['key'])}") for c in compounds[:12]]
    return Meta(title, description, path,
                jsonld=[breadcrumbs(("قيّم", "/"), ("المطورون", "/developers"), (name, path))],
                body=_summary(f"ريسيل {both_names(developer)} مقابل أسعاره اليوم", description, facts=facts, links=links))


def district_meta(district: dict | None, key: str) -> Meta:
    if not district:
        return not_found(f"/districts/{quote(key)}")
    name = place_ar(district["name"])
    title = f"أفضل فرص الريسيل في {name} اليوم — أسعار المتر كاش وتقسيط | قيّم"
    main = _primary_class(district.get("classes") or [])
    opportunities = district.get("opportunities") or {}
    good = opportunities.get("strong", 0) + opportunities.get("good", 0)
    parts = [f"{district['units']} وحدة ريسيل في {district.get('compound_count', 0)} كمبوند في {name}"]
    if main and main.get("median_asking_ppm"):
        parts.append(f"متوسط سعر المتر {ppm_ar(main['median_asking_ppm'])}")
    parts.append(f"{good} فرصة قوية أو جيدة مقارنة بسعر المطور والوحدات المماثلة")
    description = "، ".join(parts) + "."
    faq = district_faq(district)
    path = f"/districts/{quote(district['key'])}"
    compounds = district.get("compounds") or []
    facts = [f"{name_ar(c)}: {c['units']} وحدة" + (f"، {gap_ar(c['median_gap'], 'المطور')}" if c.get("median_gap") is not None else "")
             for c in compounds[:12]]
    links = [(name_ar(c), f"/compounds/{quote(c['key'])}") for c in compounds[:12]]
    links.append((f"كل وحدات {name}", f"/units?district={quote(district['key'])}"))
    jsonld = [breadcrumbs(("قيّم", "/"), ("المناطق", "/districts"), (name, path))] + ([faq_jsonld(faq)] if faq else [])
    return Meta(title, description, path, jsonld=jsonld,
                body=_summary(f"فرص الريسيل في {name}", description, facts=facts, faq=faq, links=links))


def not_found(path: str) -> Meta:
    return Meta("الصفحة غير موجودة | قيّم", "هذه الصفحة غير متاحة في قيّم.", path, index=False, status=404)


def private_meta(path: str) -> Meta:
    return Meta(f"{BRAND} — كل إعلان في الميزان", "قيّم يقارن كل وحدة ريسيل في مصر بسعر المطور اليوم وبالوحدات المماثلة.",
                path, index=False)


def clean_path(path: str) -> str:
    path = "/" + path.strip("/")
    return path


async def page_meta(path: str, query: dict[str, str], load: Loader) -> Meta:
    """The head for one public route. `load(kind, key)` returns a published document or None:
    kinds are overview, unit_detail, compound, developer, district."""
    path = clean_path(path)
    if path == "/":
        return home_meta(await load("overview", ""))
    if path.startswith(PRIVATE) or path in {p.rstrip("/") for p in PRIVATE}:
        return private_meta(path)
    if path == "/evaluate":
        return evaluate_meta(query)
    if path in STATIC:
        title, description = STATIC[path]
        if path == "/units" and query.get("price_dropped") == "true":
            title = "وحدات ريسيل نزل سعرها مؤخرًا — مقارنة بسعر المطور | قيّم"
        return Meta(title, description, path, body=_summary(title.split(" | ")[0], description, links=NAV))
    match = re.fullmatch(r"/(units|compounds|developers|districts)/([^/]+)", path)
    if match:
        kind, key = match.groups()
        key = unquote(key)
        if kind == "units":
            if not key.isdigit() or len(key) > 12:
                return not_found(path)
            return unit_meta(await load("unit_detail", key), key)
        document = await load(kind[:-1], key)
        return {"compounds": compound_meta, "developers": developer_meta, "districts": district_meta}[kind](document, key)
    return not_found(path)


# --- rendering -------------------------------------------------------------------------

def _attr(value: str) -> str:
    return escape(value, quote=True)


def absolute(url: str) -> str:
    return url if url.startswith("https://") else SITE + url


def render(template: str, meta: Meta, *, staging: bool = False) -> str:
    """index.html with this route's head and summary. The template's own tags are replaced, not duplicated."""
    title = ("[Staging] " if staging else "") + meta.title
    canonical = SITE + meta.path
    tags = [
        f'<link rel="canonical" href="{_attr(canonical)}" />',
        f'<meta property="og:site_name" content="{BRAND}" />',
        f'<meta property="og:locale" content="ar_EG" />',
        f'<meta property="og:locale:alternate" content="en_GB" />',
        f'<meta property="og:type" content="{_attr(meta.kind)}" />',
        f'<meta property="og:title" content="{_attr(meta.title)}" />',
        f'<meta property="og:description" content="{_attr(meta.description)}" />',
        f'<meta property="og:url" content="{_attr(canonical)}" />',
        f'<meta property="og:image" content="{_attr(absolute(meta.image))}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{_attr(meta.title)}" />',
        f'<meta name="twitter:description" content="{_attr(meta.description)}" />',
        f'<meta name="twitter:image" content="{_attr(absolute(meta.image))}" />',
    ]
    if not meta.index and not staging:  # a staging template already carries noindex
        tags.append('<meta name="robots" content="noindex,follow" />')
    for item in meta.jsonld:
        # "</" cannot close the script element from inside a JSON string.
        data = json.dumps(item, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        tags.append(f'<script type="application/ld+json">{data}</script>')
    html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{escape(title)}</title>", template, count=1, flags=re.S)
    html = re.sub(r'<meta\s+name="description"\s+content="[^"]*"\s*/?>',
                  lambda _: f'<meta name="description" content="{_attr(meta.description)}" />', html, count=1, flags=re.S)
    html = html.replace("</head>", "    " + "\n    ".join(tags) + "\n  </head>", 1)
    if meta.body:
        html = html.replace('<div id="root"></div>', f'<div id="root">{meta.body}</div>', 1)
    return html


def canonical_redirect(url: str) -> str | None:
    """www → apex, with the path and query kept: one host collects every link."""
    parts = urlsplit(url)
    if (parts.hostname or "") in REDIRECT_HOSTS:
        return urlunsplit(("https", CANONICAL_HOST, parts.path or "/", parts.query, ""))
    return None


def query_dict(query: str) -> dict[str, str]:
    return {key: values[-1] for key, values in parse_qs(query, keep_blank_values=False).items()}


# --- sitemap and robots ----------------------------------------------------------------

SECTIONS = ("/", "/evaluate", "/units", "/compounds", "/developers", "/districts", "/methodology")


def sitemap_xml(paths: list[str], lastmod: date | str | None) -> str:
    stamp = f"<lastmod>{lastmod.isoformat() if isinstance(lastmod, date) else lastmod}</lastmod>" if lastmod else ""
    rows = "".join(f"<url><loc>{escape(SITE + path)}</loc>{stamp}</url>" for path in dict.fromkeys(paths))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n')


def sitemap_paths(compounds: list[str], developers: list[str], districts: list[str], units: list[int]) -> list[str]:
    return [*SECTIONS, *(f"/districts/{quote(k)}" for k in districts), *(f"/compounds/{quote(k)}" for k in compounds),
            *(f"/developers/{quote(k)}" for k in developers), *(f"/units/{i}" for i in units)]


def robots_txt(staging: bool = False) -> str:
    if staging:
        return "User-agent: *\nDisallow: /\n"
    # /api stays crawlable: search engines render the app, which reads it.
    return ("User-agent: *\nAllow: /\nDisallow: /compare\nDisallow: /watchlist\nDisallow: /sheet/\n\n"
            f"Sitemap: {SITE}/sitemap.xml\n")


def llms_txt() -> str:
    """A short map of the site for AI assistants and answer engines (llmstxt.org)."""
    return f"""# Qayem (قيّم)

> Egypt's property price guide for regular buyers: what resale and new units cost by district, compound
> and developer, in today's money, compared with the developer's current price for a similar unit.
> Figures are asking and contract prices from public listings and developers' published prices; Egypt
> publishes no resale sale prices. Arabic first, English available.

## Guides

- [Districts]({SITE}/districts): prices per m² by unit type, resale against new, history and buyer questions per district
- [Compounds]({SITE}/compounds): each compound's resale prices against the developer's current price, delivery and payment terms
- [Developers]({SITE}/developers): each developer's resale market against its own prices today, and its delivery record
- [Price check]({SITE}/evaluate): is a specific unit's price a good one, against the developer and similar units

## How the figures are made

- [Methodology]({SITE}/methodology): the comparison rules, the cash-today conversion, sources, coverage and limits
- [Privacy]({SITE}/privacy): what Qayem keeps, and that it keeps no personal data from listings
- [Sitemap]({SITE}/sitemap.xml): every district, compound and developer page

Please cite figures with their month and link the page they come from.
"""


# Thin pages are left out of the sitemap (they stay reachable and indexable through links).
SITEMAP_MIN_UNITS = 3


def share_text(unit: dict) -> str:
    """The one-line verdict used when a unit is shared (kept in step with the website's share button)."""
    meta = unit_meta({"unit": unit}, str(unit["id"]))
    return f"{meta.title.removesuffix(' | قيّم')}\n{SITE}/units/{unit['id']}"


def utm(path: str, source: str, medium: str, campaign: str = "") -> str:
    params = {"utm_source": source, "utm_medium": medium, **({"utm_campaign": campaign} if campaign else {})}
    return f"{SITE}{path}{'&' if '?' in path else '?'}{urlencode(params)}"
