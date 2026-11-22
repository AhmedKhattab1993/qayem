"""Cash-equivalent pricing and entity-key helpers for Egyptian property listings.

A unit sold on a multi-year instalment plan is not comparable to a cash unit until its remaining
instalments are discounted to today's money (the Central Bank of Egypt overnight deposit rate, or
DISCOUNT_RATE when no rate has been fetched). The legacy fair-value model was retired once Qayem
moved to market aggregates and direct comparisons.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
import re
from typing import Iterable

DISCOUNT_RATE = 0.20  # fallback annual rate when CBE's overnight deposit rate is unavailable
PAYMENT_INTERVAL_MONTHS = 3  # plans are modelled as equal quarterly payments

CLASSES = {
    "apartment": "apartment", "studio": "apartment", "duplex": "apartment",
    "penthouse": "apartment", "loft": "apartment", "roof": "apartment",
    "chalet": "chalet", "cabin": "chalet",
    "villa": "house", "townhouse": "house", "twinhouse": "house",
    "house": "house", "family house": "house",
}
FINISHING = {
    "finished": "finished", "fully_finished": "finished", "lux": "finished", "super_lux": "finished",
    "extra_super_lux": "finished", "unfurnished": "finished", "furnished": "furnished",
    "semi_finished": "semi_finished", "core_shell": "core_shell",
}
READY_WORDS = {"ready", "ready_to_move", "new", "used", "فوري", "immediate", "delivered"}
DELIVERY_BUCKETS = ("ready", "under_1y", "1_2y", "2_3y", "3y_plus", "unknown")
PLAN_BUCKETS = ("cash", "under_3y", "3_6y", "6_9y", "9y_plus")
DISTRICT_ALIASES = {
    "fifth settlement": "New Cairo", "5th settlement": "New Cairo", "the 5th settlement": "New Cairo",
    "new cairo city": "New Cairo", "التجمع الخامس": "New Cairo", "القاهرة الجديدة": "New Cairo",
    "التجمع الأول": "New Cairo", "التجمع الثالث": "New Cairo", "التجمع السادس": "6th settlement",
    "sheikh zayed": "El Sheikh Zayed", "el sheikh zayed city": "El Sheikh Zayed", "الشيخ زايد": "El Sheikh Zayed",
    "زايد الجديدة": "New Zayed", "6 october": "6th of October City", "6th of october": "6th of October City",
    "october": "6th of October City", "السادس من أكتوبر": "6th of October City", "6 أكتوبر": "6th of October City",
    "6 اكتوبر": "6th of October City", "حدائق أكتوبر": "October Gardens", "أكتوبر الجديدة": "Northern Expansion",
    "new capital": "New Capital City", "new administrative capital": "New Capital City",
    "العاصمة الإدارية الجديدة": "New Capital City", "العاصمة الادارية الجديدة": "New Capital City",
    "mostakbal city": "Mostakbal City", "el mostakbal": "Mostakbal City", "مدينة المستقبل": "Mostakbal City",
    "المستقبل سيتي": "Mostakbal City", "مدينتي": "Madinaty", "الشروق": "El Shorouk",
    "هليوبوليس الجديدة": "New Heliopolis", "مدينة نصر": "Nasr City", "زهراء المعادي": "Maadi",
    "الساحل الشمالي": "North Coast", "north coast-sahel": "North Coast", "رأس الحكمة": "Ras El Hekma",
    "سيدي عبد الرحمن": "Sidi Abdel Rahman", "العلمين الجديدة": "Al Alamein", "العلمين": "Al Alamein",
    "الضبعة": "Al Dabaa", "العين السخنة": "Ain Sokhna", "مكادي": "Makadi", "رأس سدر": "Ras Sudr",
    "الإسكندرية": "Alexandria", "الاسكندرية": "Alexandria",
}
_DEVELOPER_NOISE = re.compile(
    r"\b(developments?|developers?|properties|property|real estate|group|holdings?|egypt|misr|company|co|"
    r"for|investment|investments|urban|the)\b|\(.*?\)"
)
_ARABIC_NOISE = re.compile(r"(شركة|شركه|للتطوير|التطوير|العقاري|العقارية|العقارى|للتنمية|العمراني|العمرانية|جروب|مجموعة|"
                           r"القابضة|للاستثمار|للإسكان|والتعمير|ديفلوبمنتس|ديفيلوبمنتس|ايجيبت|إيجيبت)")
DEVELOPER_ALIASES = {
    "tmg": "talaatmoustafa", "talaat moustafa": "talaatmoustafa", "طلعت مصطفى": "talaatmoustafa",
    "هايد بارك": "hydepark", "هايدبارك": "hydepark", "بالم هيلز": "palmhills", "بالم هيلز للتعمير": "palmhills",
    "مدينة مصر": "madinetmasr", "مدينه مصر": "madinetmasr", "حسن علام": "hassanallam",
    "ماونتن فيو": "mountainview", "ماونتن فيو مصر": "mountainview", "مصر ايطاليا": "italia", "مصر إيطاليا": "italia",
    "الكازار": "ilcazar", "سوديك": "sodic", "إعمار": "emaar", "اعمار": "emaar", "إعمار مصر": "emaar",
    "اعمار مصر": "emaar", "أورا": "ora", "اورا": "ora", "تطوير مصر": "tatweer", "لافيستا": "lavista",
    "لا فيستا": "lavista", "بدر الدين": "badreldin", "معمار المرشدي": "maamarelmorshedy",
    "المراسم": "almarasem", "مراكز": "marakez", "سيتي إيدج": "cityedge", "سيتي ايدج": "cityedge",
    "الأهلي صبور": "alahlysabbour", "الاهلي صبور": "alahlysabbour", "أوراسكوم": "orascom", "اوراسكوم": "orascom",
}


def slug(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^\w؀-ۿ]+", "-", text.casefold()).strip("-_")


def developer_key(name: str | None) -> str:
    if not name:
        return ""
    lowered = " ".join(name.casefold().split())
    if lowered in DEVELOPER_ALIASES:
        return DEVELOPER_ALIASES[lowered]
    latin = re.sub(r"[^a-z0-9()& ]+", " ", lowered)
    if re.search(r"[a-z]{3}", latin) and re.search(r"[؀-ۿ]", lowered):
        lowered = " ".join(latin.split())  # bilingual names: the Latin part is the stable one
    if re.search(r"[؀-ۿ]", lowered):
        arabic = " ".join(_ARABIC_NOISE.sub(" ", lowered).split())
        if arabic in DEVELOPER_ALIASES:
            return DEVELOPER_ALIASES[arabic]
        return re.sub(r"[^\w؀-ۿ]+", "", arabic) or re.sub(r"[^\w؀-ۿ]+", "", lowered)
    if "talaat moustafa" in lowered or "tmg" in lowered.split():
        return "talaatmoustafa"
    stripped = re.sub(r"[^\w؀-ۿ]+", "", _DEVELOPER_NOISE.sub(" ", lowered))
    return stripped or re.sub(r"[^\w؀-ۿ]+", "", lowered)


_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
                              **{chr(0x0660 + d): str(d) for d in range(10)}, **{chr(0x06F0 + d): str(d) for d in range(10)}})
_DIACRITICS = re.compile(r"[ً-ٰٟـ]")
_COMPOUND_WORDS = re.compile(r"\b(compound|كمبوند|كومبوند|كمباوند|مشروع|project)\b")


def fold(text: str | None) -> str:
    """Spelling-insensitive form: Arabic letter variants, diacritics, case and separators ignored."""
    if not text:
        return ""
    folded = _DIACRITICS.sub("", text.casefold()).translate(_ARABIC_FOLD)
    return re.sub(r"[\W_]+", "", _COMPOUND_WORDS.sub(" ", folded))


def alias_key(compound: str | None, developer: str | None) -> str | None:
    """Key of one compound/developer spelling pair in the entity_aliases table."""
    compound_part = fold(compound)
    return f"{compound_part}|{fold(developer_key(developer))}" if compound_part else None


def canonical_district(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = " ".join(name.split())
    return DISTRICT_ALIASES.get(cleaned.casefold(), cleaned)


def finishing_class(value: str | None) -> str:
    return FINISHING.get((value or "").casefold(), "unknown")


def delivery_bucket(delivery_date: str | None, delivery_status: str | None, today: date) -> tuple[str, float | None]:
    """→ (bucket, years until promised handover; ≤ 0 means due or delivered)."""
    if delivery_date:
        try:
            years = (date.fromisoformat(delivery_date[:10]) - today).days / 365.25
        except ValueError:
            years = None
        if years is not None:
            if years <= 0:
                return "ready", round(years, 2)
            bucket = "under_1y" if years <= 1 else "1_2y" if years <= 2 else "2_3y" if years <= 3 else "3y_plus"
            return bucket, round(years, 2)
    if (delivery_status or "").casefold() in READY_WORDS:
        return "ready", None
    return "unknown", None


def plan_bucket(payment: dict) -> str:
    """Remaining plan length. The market discounts long plans less steeply than a flat rate,
    so the model learns that convention instead of assuming it."""
    if payment["terms"] in ("cash", "unknown"):
        return "cash"
    years = payment.get("years")
    if years is None:
        return "unknown"
    return "under_3y" if years < 3 else "3_6y" if years < 6 else "6_9y" if years < 9 else "9y_plus"


def present_value_factor(months: int, rate: float = DISCOUNT_RATE) -> float:
    """Value today of 1 EGP of remaining balance paid in equal instalments over `months`."""
    payments = max(1, round(months / PAYMENT_INTERVAL_MONTHS))
    step = months / payments / 12
    return sum(1 / (1 + rate) ** (step * (index + 1)) for index in range(payments)) / payments


def payment_terms(price: float, down_payment: float | None, months: int | None,
                  installments: bool | None, cash_when_not_installment: bool,
                  rate: float = DISCOUNT_RATE) -> dict:
    """Classify the payment structure and derive today's-money cost where terms are known.

    terms: 'cash' | 'plan' | 'partial' (installments, term unknown) | 'unknown'.
    """
    if installments and down_payment is not None and months:
        remaining = max(0.0, price - down_payment)
        present = down_payment + remaining * present_value_factor(months, rate)
        return {"terms": "plan", "cash_equivalent": round(present), "remaining": round(remaining),
                "remaining_share": round(remaining / price, 4), "years": round(months / 12, 1),
                "discount": round(1 - present / price, 4)}
    if installments:
        return {"terms": "partial", "cash_equivalent": None, "remaining": None,
                "remaining_share": None, "years": None, "discount": None}
    if cash_when_not_installment:
        return {"terms": "cash", "cash_equivalent": round(price), "remaining": 0,
                "remaining_share": 0.0, "years": 0.0, "discount": 0.0}
    return {"terms": "unknown", "cash_equivalent": None, "remaining": None,
            "remaining_share": None, "years": None, "discount": None}


def majority(values: Iterable[str | None]) -> str | None:
    counted = Counter(value for value in values if value)
    return counted.most_common(1)[0][0] if counted else None
