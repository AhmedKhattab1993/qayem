"""Normalization helpers: Arabic/English text → canonical field values.

Everything that turns messy classifieds text (Arabic numerals, dual forms,
negotiable prices, finishing grades) into the unified schema lives here so
all sources share one interpretation.
"""

from __future__ import annotations

import re

# Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digits → ASCII.
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def to_western_digits(text: str) -> str:
    return text.translate(ARABIC_DIGITS) if text else text


def parse_number(text: str | None) -> float | None:
    """Extract the first number from free text: '4,900,000' → 4900000.0."""
    if not text:
        return None
    cleaned = to_western_digits(text)
    cleaned = re.sub(r"[,\s٬']", "", cleaned)
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


_NEGOTIABLE_RE = re.compile(r"قابل للتفاوض|negotiable|أو بأقرب|او بأقرب", re.IGNORECASE)


def parse_price(text: str | None) -> tuple[float | None, bool]:
    """→ (price, is_negotiable)."""
    if not text:
        return None, False
    return parse_number(text), bool(_NEGOTIABLE_RE.search(text))


def parse_area(text: str | None) -> float | None:
    """'155 متر', '130 m2', '2,500 م²' → 155.0. Returns the *first* number
    which in listing copy is the built area."""
    if not text:
        return None
    return parse_number(text)


_DUAL_RE = re.compile(r"(\S+)ين\b")  # غرفتين/حمامين — Arabic dual form
_ARABIC_COUNT_WORDS = {
    "واحد": 1, "واحدة": 1,
    "اثنان": 2, "اثنين": 2, "غرفتين": 2, "حمامين": 2,
    "ثلاث": 3, "ثلاثة": 3, "ثلاث غرف": 3,
    "أربع": 4, "اربع": 4,
    "خمس": 5, "ست": 6, "ستة": 6, "سبع": 7, "ثمان": 8, "تسع": 9, "عشر": 10,
}


def parse_count(text: str | None) -> int | None:
    """Number of rooms/baths from text: '3 غرف' → 3, 'غرفتين' → 2, '2 Bedrooms' → 2."""
    if not text:
        return None
    cleaned = to_western_digits(text)
    num = re.search(r"\d+", cleaned)
    if num:
        return int(num.group())
    # dual form: غرفة→غرفتين, حمامة→حمامين
    if _DUAL_RE.search(cleaned) or re.search(r"غرفتين|حمامين|اثنين", cleaned):
        return 2
    for word, value in _ARABIC_COUNT_WORDS.items():
        if word in cleaned:
            return value
    return None


# --- property type -----------------------------------------------------------

_PROPERTY_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"twin\s*house|توين", "twinhouse"),
    (r"town\s*house|تاون", "townhouse"),
    (r"pent\s*house|بينت|بنتا?\s*هاوس", "penthouse"),
    (r"duplex|دوبلكس|دوبلكس", "duplex"),
    (r"studio|ستوديو", "studio"),
    (r"villa|فيلا", "villa"),
    (r"chalet|شاليه", "chalet"),
    (r"apartment|شقة|شقق", "apartment"),
    (r"رووف|roof", "roof"),
    (r"أرض|ارض|land", "land"),
    (r"عمارة|building", "building"),
    (r"مكتب|ادارى|إداري|office", "office"),
    (r"محل|متجر|shop|retail", "shop"),
    (r"عيادة|صيدلية|clinic|pharmacy", "clinic"),
    (r"warehouse|مخزن", "warehouse"),
]
CANONICAL_PROPERTY_TYPES = frozenset(canonical for _, canonical in _PROPERTY_TYPE_PATTERNS)


def detect_property_type(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for pattern, canonical in _PROPERTY_TYPE_PATTERNS:
        if re.search(pattern, lowered):
            return canonical
    return None


# --- finishing ---------------------------------------------------------------

_FINISHING_PATTERNS: list[tuple[str, str]] = [
    (r"إكسترا سوبر لوكس|اكسترا سوبر لوكس|extra\s*super\s*lux", "extra_super_lux"),
    (r"سوبر لوكس|super\s*lux", "super_lux"),
    (r"لوكس\b|lux\b|fully\s*finished|مكمل التشطيب", "lux"),
    (r"نصف تشطيب|نص تشطيب|نصف تشطبات|semi\s*finished", "semi_finished"),
    (r"على الطوب الأحمر|الطوب الاحمر|بدون تشطيب|core\s*(&|and)\s*shell|shell", "core_shell"),
]


def detect_finishing(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for pattern, canonical in _FINISHING_PATTERNS:
        if re.search(pattern, lowered):
            return canonical
    return None


# --- delivery status ---------------------------------------------------------

_DELIVERY_PATTERNS: list[tuple[str, str]] = [
    (r"استلام فوري|استلام حالى|استلام حالي|ready\s*to\s*(move|occupy)", "ready_to_move"),
    (r"قيد الإنشاء|قيد الانشاء|تحت الإنشاء|under\s*construction|على الخريطة", "under_construction"),
    (r"جديدة أول ساكن|جديدة اول ساكن|أول ساكن", "new"),
    (r"مستعمل|used|بالاستلام", "used"),
]


def detect_delivery_status(text: str | None) -> str | None:
    if not text:
        return None
    for pattern, canonical in _DELIVERY_PATTERNS:
        if re.search(pattern, text):
            return canonical
    return None


# --- governorates ------------------------------------------------------------

_GOVERNORATES = {
    "القاهرة": "cairo", "cairo": "cairo",
    "الجيزة": "giza", "giza": "giza", "6 أكتوبر": "giza", "6 اكتوبر": "giza",
    "الشيخ زايد": "giza",
    "الإسكندرية": "alexandria", "الاسكندرية": "alexandria", "alexandria": "alexandria",
    "القليوبية": "qalyubia", "qalyubia": "qalyubia",
    "الدقهلية": "dakahlia", "dakahlia": "dakahlia",
    "الشرقية": "sharqia", "sharqia": "sharqia",
    "الغربية": "gharbia", "gharbia": "gharbia",
    "المنوفية": "menoufia", "menoufia": "menoufia",
    "البحيرة": "beheira", "beheira": "beheira",
    "كفر الشيخ": "kafr_el_sheikh", "kafr elsheikh": "kafr_el_sheikh",
    "دمياط": "damietta", "damietta": "damietta",
    "بورسعيد": "port_said", "بور سعيد": "port_said", "port said": "port_said",
    "الإسماعيلية": "ismailia", "الاسماعيلية": "ismailia", "ismailia": "ismailia",
    "السويس": "suez", "suez": "suez",
    "شمال سيناء": "north_sinai", "جنوب سيناء": "south_sinai",
    "مطروح": "matrouh", "matrouh": "matrouh",
    "البحر الأحمر": "red_sea", "البحر الاحمر": "red_sea", "red sea": "red_sea",
    "الوادي الجديد": "new_valley",
    "بني سويف": "beni_suef", "beni suef": "beni_suef",
    "المنيا": "minya", "minya": "minya",
    "الفيوم": "fayoum", "fayoum": "fayoum",
    "أسيوط": "assiut", "اسيوط": "assiut", "assiut": "assiut",
    "سوهاج": "sohag", "sohag": "sohag",
    "قنا": "qena", "qena": "qena",
    "الأقصر": "luxor", "الاقصر": "luxor", "luxor": "luxor",
    "أسوان": "aswan", "اسوان": "aswan", "aswan": "aswan",
    "العاصمة الإدارية الجديدة": "cairo", "العاصمة الادارية الجديدة": "cairo",
    "new administrative capital": "cairo",
}


def normalize_governorate(text: str | None) -> str | None:
    if not text:
        return None
    return _GOVERNORATES.get(text.strip())


# --- seller / resale heuristics ---------------------------------------------

_OWNER_RE = re.compile(r"من المالك مباشرة|من المالك|by owner|no broker")
_BROKER_RE = re.compile(r"بواسطة سمسار|سمسار|وسيط عقاري|broker|agent")
_DEVELOPER_RE = re.compile(r"من المطور|المطور مباشرة|by developer")


def detect_seller_type(text: str | None) -> str | None:
    if not text:
        return None
    if _DEVELOPER_RE.search(text):
        return "developer"
    if _OWNER_RE.search(text):
        return "owner"
    if _BROKER_RE.search(text):
        return "broker"
    return None


# Signals that a unit is secondary-market rather than primary/off-plan.
# Only *positive* evidence sets is_resale=True; absence leaves it unknown.
_RESALE_POSITIVE: list[tuple[str, str]] = [
    (r"\bresale\b", "keyword 'resale'"),
    (r"ريسيل", "keyword 'ريسيل' (resale)"),
    (r"تمليك", "«تمليك» (freehold — secondary-market phrasing)"),
    (r"من المالك", "owner-direct sale (secondary market)"),
]


def classify_resale(text: str | None) -> tuple[bool | None, str | None]:
    """→ (is_resale or None-if-unknown, evidence)."""
    if not text:
        return None, None
    for pattern, evidence in _RESALE_POSITIVE:
        if re.search(pattern, text):
            return True, evidence
    return None, None


# OpenSooq-style highlights: "2 Bedrooms » 2 Bathrooms » 130 m2"
_HIGHLIGHT_PARTS = re.compile(r"»|\||;|،")


def parse_highlights(highlights: str | None) -> dict[str, float | int | None]:
    """Parse an OpenSooq highlights string into bedrooms/bathrooms/area."""
    out: dict[str, float | int | None] = {"bedrooms": None, "bathrooms": None, "area_m2": None}
    if not highlights:
        return out
    for part in _HIGHLIGHT_PARTS.split(to_western_digits(highlights)):
        part_l = part.lower()
        if "bedroom" in part_l or "غرف" in part_l:
            out["bedrooms"] = parse_count(part)
        elif "bathroom" in part_l or "حمام" in part_l:
            out["bathrooms"] = parse_count(part)
        elif "m2" in part_l or "م²" in part_l or "متر" in part_l:
            out["area_m2"] = parse_number(part)
    return out


def extract_phone(text: str | None) -> str | None:
    """First Egyptian mobile number from text: 010/011/012/015, 11 digits."""
    if not text:
        return None
    cleaned = to_western_digits(text)
    match = re.search(r"(?:\+?20|0)?1(?:0|1|2|5)\d{8}", cleaned)
    return match.group() if match else None
