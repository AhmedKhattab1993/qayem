"""Market districts: the areas buyers mean («التجمع», «الشيخ زايد», «الساحل»), not official boundaries.

Every source spells places its own way (Aqarmap alone has over a thousand district spellings, many
of them streets or compound names). `resolve` maps a listing's district, compound, link and title
to one market district, so figures from every source add up in the same place. The registry is
Qayem's own layer and is versioned here (docs/STRATEGY.md, 7.2); its centroids and outlines come
from OpenStreetMap (`src/qayem/data/market_districts.geojson`, © OpenStreetMap contributors, ODbL).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from urllib.parse import unquote, urlsplit

GREATER_CAIRO, ALEXANDRIA, NORTH_COAST, RED_SEA, SINAI, DELTA, CANAL, UPPER = (
    "greater_cairo", "alexandria", "north_coast", "red_sea", "sinai", "delta", "canal", "upper_egypt")
REGION_NAMES = {
    GREATER_CAIRO: ("Greater Cairo", "القاهرة الكبرى"), ALEXANDRIA: ("Alexandria", "الإسكندرية"),
    NORTH_COAST: ("North Coast", "الساحل الشمالي"), RED_SEA: ("Red Sea", "البحر الأحمر"),
    SINAI: ("Sinai", "سيناء"), DELTA: ("Delta", "الدلتا"), CANAL: ("Suez Canal", "مدن القناة"),
    UPPER: ("Upper Egypt", "الصعيد"),
}


@dataclass(frozen=True)
class District:
    key: str
    name: str
    name_ar: str
    region: str
    lat: float
    lon: float
    aliases: tuple[str, ...]
    in_compounds: bool = True  # mostly new compounds (False: an established city market)


def _d(key, name, name_ar, region, lat, lon, *aliases, in_compounds=True):
    return District(key, name, name_ar, region, lat, lon, (name, name_ar, *aliases), in_compounds)


# Order matters only for ties: a longer alias always wins over a shorter one it contains
# ("new zayed" over "zayed", "حدائق اكتوبر" over "اكتوبر"). Keys keep the website's existing URLs.
DISTRICTS: tuple[District, ...] = (
    # --- East Cairo -------------------------------------------------------------------------
    _d("new-cairo", "New Cairo", "القاهرة الجديدة", GREATER_CAIRO, 30.0074, 31.4913,
       "new cairo city", "fifth settlement", "5th settlement", "the 5th settlement", "el tagamoa", "tagamoa",
       "first settlement", "1st settlement", "third settlement", "التجمع الخامس", "التجمع الاول", "التجمع الثالث",
       "التجمع", "القاهره الجديده", "el narges", "new narges", "el banafsag", "el yasmeen", "el andalus",
       "golden square", "north investors", "south investors", "small investor", "el lotus", "lotus north",
       "lotus south", "south new cairo", "american university housing", "el choueifat", "choueifat",
       "katameya", "kattameya", "القطامية", "mukhabarat land", "el koronfel", "beit al watan", "بيت الوطن",
       "النرجس", "اللوتس", "الشويفات", "جنوب الاكاديمية", "90th street", "التسعين"),
    _d("6th-settlement", "6th settlement", "التجمع السادس", GREATER_CAIRO, 30.0300, 31.5700,
       "sixth settlement", "6th settlement new cairo"),
    _d("el-rehab", "El Rehab", "الرحاب", GREATER_CAIRO, 30.0605, 31.4906, "rehab city", "rehab", "al rehab",
       "مدينة الرحاب"),
    _d("madinaty", "Madinaty", "مدينتي", GREATER_CAIRO, 30.0969, 31.6359, "madinaty city"),
    _d("el-shorouk", "El Shorouk", "الشروق", GREATER_CAIRO, 30.1434, 31.6286, "shorouk city", "el shorouk city",
       "al shorouk", "shorouk", "مدينة الشروق"),
    _d("el-obour", "El Obour", "العبور", GREATER_CAIRO, 30.2286, 31.4801, "obour city", "obour", "el obour city",
       "مدينة العبور", "العبور الجديدة"),
    _d("badr-city", "Badr City", "مدينة بدر", GREATER_CAIRO, 30.1360, 31.7158, "badr", "بدر"),
    _d("mostakbal-city", "Mostakbal City", "مدينة المستقبل", GREATER_CAIRO, 30.1300, 31.5800, "el mostakbal",
       "mostakbal", "future city", "المستقبل سيتي", "مستقبل سيتي", "المستقبل"),
    _d("new-capital-city", "New Capital City", "العاصمة الإدارية الجديدة", GREATER_CAIRO, 30.0196, 31.7600,
       "new administrative capital", "new capital", "administrative capital", "el asema el edarya",
       "العاصمه الاداريه", "العاصمة الادارية", "العاصمة", "new capital gardens", "capital gardens",
       "حدائق العاصمة", "r7", "r8", "r3", "r5", "downtown new capital", "mu23", "mu 23", "ls1"),
    _d("new-heliopolis", "New Heliopolis", "هليوبوليس الجديدة", GREATER_CAIRO, 30.1300, 31.6650,
       "new heliopolis city"),
    _d("heliopolis", "Heliopolis", "مصر الجديدة", GREATER_CAIRO, 30.0911, 31.3225, "masr el gedida",
       "heliopolis masr el gedida", "el nozha", "nozha", "sheraton", "شيراتون", "النزهة", "ألماظة", "almaza",
       "el korba", "roxy"),
    _d("nasr-city", "Nasr City", "مدينة نصر", GREATER_CAIRO, 30.0566, 31.3301, "madinat nasr", "nasr city cairo",
       "makram ebeid", "abbas el akkad", "el hay el asher", "zahraa nasr city"),
    _d("mokattam", "Mokattam", "المقطم", GREATER_CAIRO, 30.0233, 31.3006, "el mokattam", "al mokattam"),
    _d("maadi", "Maadi", "المعادي", GREATER_CAIRO, 29.9602, 31.2569, "el maadi", "zahraa el maadi",
       "zahraa al maadi", "زهراء المعادي", "degla", "sarayat el maadi", "new maadi"),
    _d("central-cairo", "Central Cairo", "وسط القاهرة", GREATER_CAIRO, 30.0459, 31.2400,
       "downtown cairo", "central cairo", "downtown", "وسط البلد", "zamalek", "الزمالك", "garden city cairo",
       "el manial", "manial", "المنيل", "old cairo", "مصر القديمة", "abbasiya", "العباسية", "shubra", "شبرا",
       "ain shams", "عين شمس", "matariya", "المطرية", "el marg", "المرج", "hadayek al kobba", "hadayek el kobba",
       "حدائق القبة", "zaytoun", "el zaytoun", "الزيتون", "gesr al suez", "جسر السويس", "el salam city",
       "مدينة السلام", "el sayeda zeinab", "السيدة زينب", "dar el salam", "دار السلام", "el basatin"),
    _d("helwan", "Helwan", "حلوان", GREATER_CAIRO, 29.8500, 31.3340, "15th of may", "15 مايو", "مايو"),
    # --- West Cairo / Giza --------------------------------------------------------------------
    _d("6th-of-october-city", "6th of October City", "مدينة ٦ أكتوبر", GREATER_CAIRO, 29.9389, 30.9175,
       "6 october", "6th of october", "6th october", "sixth of october", "october city", "october",
       "6 of october", "السادس من اكتوبر", "6 اكتوبر", "٦ اكتوبر", "اكتوبر", "new sphinx", "sphinx city",
       "سفنكس الجديدة", "el hay el motamayez", "west somid", "el hosary", "الحصري", "dreamland", "دريم لاند",
       "touristic area b", "mariotia", "المريوطية"),
    _d("october-gardens", "October Gardens", "حدائق أكتوبر", GREATER_CAIRO, 29.9200, 31.0300, "hadayek october",
       "hadayek el october", "حدائق اكتوبر", "october gardens city"),
    _d("northern-expansion", "Northern Expansion", "التوسعات الشمالية", GREATER_CAIRO, 30.0500, 30.9500,
       "northern expansions", "new october", "اكتوبر الجديدة", "التوسعات الشمالية لمدينة 6 اكتوبر",
       "el tawsaat el shamaliya"),
    _d("el-sheikh-zayed", "El Sheikh Zayed", "الشيخ زايد", GREATER_CAIRO, 30.0444, 30.9800, "sheikh zayed",
       "el sheikh zayed city", "sheikh zayed city", "zayed city", "zayed", "الشيخ زايد الجديدة",
       "beverly hills zayed", "seventeenth neighborhood", "sixteenth neighborhood", "زايد",
       "october and zayed city", "october zayed city"),
    _d("new-zayed", "New Zayed", "زايد الجديدة", GREATER_CAIRO, 30.0800, 30.9200, "new sheikh zayed", "new zayed city"),
    _d("mohandessin-dokki", "Mohandessin & Dokki", "المهندسين والدقي", GREATER_CAIRO, 30.0500, 31.2050,
       "mohandessin", "mohandeseen", "المهندسين", "dokki", "الدقي", "agouza", "العجوزة", "lebanon st",
       "gameat el dewal el arbabeya", "شارع جامعة الدول"),
    _d("haram-faisal", "Haram & Faisal", "الهرم وفيصل", GREATER_CAIRO, 29.9950, 31.1550, "haram", "el haram",
       "faisal", "king faisal st", "الهرم", "فيصل", "al haram", "el omraniya", "omraniya", "العمرانية"),
    _d("hadayek-al-ahram", "Hadayek al-Ahram", "حدائق الأهرام", GREATER_CAIRO, 29.9650, 31.0950,
       "hadayek el ahram", "pyramids gardens", "حدائق الاهرام"),
    _d("giza", "Giza", "الجيزة", GREATER_CAIRO, 30.0131, 31.2089, "giza city", "الجيزة", "الجيزه"),
    _d("10th-of-ramadan", "10th of Ramadan", "العاشر من رمضان", DELTA, 30.2950, 31.7460, "10th of ramadan city",
       "tenth of ramadan", "العاشر"),
    # --- Alexandria -------------------------------------------------------------------------
    _d("alexandria", "Alexandria", "الإسكندرية", ALEXANDRIA, 31.2156, 29.9553, "alex", "الاسكندرية", "اسكندرية",
       "smouha", "smoha", "سموحة", "sidi beshr", "sidi bishr", "miami", "montaza", "المنتزه", "agamy", "agami",
       "al agamy", "العجمي", "el hanouvel", "el bitash", "al bitash", "shatee el nakheel", "شاطئ النخيل",
       "el asafra", "asafra", "el mandara", "mandara", "gleem", "glim", "stanley", "sporting", "sidi gaber",
       "سيدي جابر", "loran", "laurent", "kafr abdo", "roushdy", "fleming", "zezenia", "cleopatra", "victoria",
       "moharram bey", "moharam bik", "el seyouf", "seyouf", "abu talat", "abu yusuf", "bianchi", "el falki",
       "muruj", "sawary", "king mariout", "كينج مريوط", "el dekhela", "eskot", "camp cesar", "ganaklis",
       "san stefano", "el ibrahimiya", "bahray el anfoshy"),
    _d("borg-el-arab", "Borg el arab", "برج العرب", ALEXANDRIA, 30.9180, 29.5650, "borg al arab", "new borg el arab",
       "برج العرب الجديدة"),
    # --- North Coast ------------------------------------------------------------------------
    _d("north-coast", "North Coast", "الساحل الشمالي", NORTH_COAST, 30.9500, 28.8000, "north coast sahel", "sahel",
       "el sahel", "الساحل", "el hamam", "الحمام", "ghazala bay", "marina", "مارينا", "marina el alamein",
       "el kilo 21", "km 21"),
    _d("sidi-heneish", "Sidi Heneish", "سيدي حنيش", NORTH_COAST, 31.1500, 27.6400, "sidi hneish"),
    _d("ras-el-hekma", "Ras El Hekma", "رأس الحكمة", NORTH_COAST, 31.1300, 27.8500, "ras el hikma", "ras al hekma",
       "راس الحكمة", "راس الحكمه"),
    _d("sidi-abdel-rahman", "Sidi Abdel Rahman", "سيدي عبد الرحمن", NORTH_COAST, 30.9700, 28.7500,
       "sidi abd el rahman", "sidi abdelrahman", "سيدي عبدالرحمن"),
    _d("al-alamein", "Al Alamein", "العلمين", NORTH_COAST, 30.8300, 28.9500, "new alamein", "el alamein",
       "alamein", "العلمين الجديدة", "new alamein city"),
    _d("al-dabaa", "Al Dabaa", "الضبعة", NORTH_COAST, 31.0300, 28.4300, "el dabaa", "dabaa", "الضبعه"),
    _d("marsa-matrouh", "Marsa Matrouh", "مرسى مطروح", NORTH_COAST, 31.3543, 27.2373, "matrouh", "mersa matruh",
       "alam al roum", "alam el roum", "علم الروم", "مطروح"),
    # --- Red Sea and Sinai ------------------------------------------------------------------
    _d("ain-sokhna", "Ain Sokhna", "العين السخنة", RED_SEA, 29.6000, 32.3200, "el sokhna", "sokhna", "ain el sokhna",
       "السخنة", "موفنبيك السخنة"),
    _d("galala-city", "Galala City", "مدينة الجلالة", RED_SEA, 29.4200, 32.4200, "galala", "el galala", "الجلالة",
       "الجلاله", "بلو هب الجلالة", "المونت جلالة", "il monte galala"),
    _d("hurghada", "Hurghada", "الغردقة", RED_SEA, 27.2579, 33.8116, "el hurghada", "الغردقه"),
    _d("el-gouna", "El Gouna", "الجونة", RED_SEA, 27.3950, 33.6780, "gouna", "الجونه"),
    _d("makadi", "Makadi", "مكادي", RED_SEA, 26.9900, 33.8800, "makadi bay", "مكادي باي"),
    _d("sahl-hasheesh", "Sahl Hasheesh", "سهل حشيش", RED_SEA, 27.0450, 33.8800, "sahl hashish"),
    _d("soma-bay", "Soma Bay", "سوما باي", RED_SEA, 26.8500, 33.9900, "somabay"),
    _d("ras-sudr", "Ras Sudr", "رأس سدر", SINAI, 29.5900, 32.7100, "ras sedr", "راس سدر"),
    _d("sharm-el-sheikh", "Sharm El Sheikh", "شرم الشيخ", SINAI, 27.9158, 34.3300, "sharm", "شرم"),
    # --- Delta, Canal and Upper Egypt (established city markets) ----------------------------
    _d("mansoura", "Mansoura", "المنصورة", DELTA, 31.0409, 31.3785, "new mansoura", "المنصورة الجديدة",
       "المنصوره", in_compounds=False),
    _d("tanta", "Tanta", "طنطا", DELTA, 30.7865, 31.0004, in_compounds=False),
    _d("zagazig", "Zagazig", "الزقازيق", DELTA, 30.5877, 31.5020, in_compounds=False),
    _d("damietta", "Damietta", "دمياط", DELTA, 31.4165, 31.8133, "new damietta", "دمياط الجديدة",
       in_compounds=False),
    _d("banha", "Banha", "بنها", DELTA, 30.4660, 31.1848, "benha", in_compounds=False),
    _d("port-said", "Port Said", "بورسعيد", CANAL, 31.2653, 32.3019, "بور سعيد", in_compounds=False),
    _d("ismailia", "Ismailia", "الإسماعيلية", CANAL, 30.5965, 32.2715, "الاسماعيلية", in_compounds=False),
    _d("suez", "Suez", "السويس", CANAL, 29.9668, 32.5498, in_compounds=False),
    _d("assiut", "Assiut", "أسيوط", UPPER, 27.1801, 31.1837, "asyut", "اسيوط", in_compounds=False),
    _d("sohag", "Sohag", "سوهاج", UPPER, 26.5591, 31.6957, in_compounds=False),
    _d("minya", "Minya", "المنيا", UPPER, 28.1099, 30.7503, in_compounds=False),
    _d("fayoum", "Fayoum", "الفيوم", UPPER, 29.3084, 30.8428, in_compounds=False),
    _d("beni-suef", "Beni Suef", "بني سويف", UPPER, 29.0661, 31.0994, in_compounds=False),
    _d("luxor", "Luxor", "الأقصر", UPPER, 25.6872, 32.6396, "الاقصر", in_compounds=False),
    _d("aswan", "Aswan", "أسوان", UPPER, 24.0889, 32.8998, "اسوان", in_compounds=False),
)
BY_KEY = {d.key: d for d in DISTRICTS}
BY_NAME = {d.name: d for d in DISTRICTS}

# A crawl scope's city limits where its listings can be: an Alexandria page lists no New Cairo flat.
SCOPE_REGIONS = {"alexandria": {ALEXANDRIA, NORTH_COAST}, "cairo": {GREATER_CAIRO, DELTA},
                 "giza": {GREATER_CAIRO}}
SCOPE_FALLBACK = {"alexandria": "alexandria", "giza": "giza"}

_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
                       **{chr(0x0660 + d): str(d) for d in range(10)}, **{chr(0x06F0 + d): str(d) for d in range(10)}})
_DIACRITICS = re.compile(r"[ً-ٰٟـ]")
_LATIN_NOISE = re.compile(r"\b(the|el|al|city|st|street|rd|road|compound|area)\b")


def fold(text: str | None) -> str:
    """Spelling-insensitive words: case, Arabic letter variants, «ال» and punctuation ignored."""
    if not text:
        return ""
    text = _DIACRITICS.sub("", text.casefold()).translate(_FOLD)
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"[^\w]+|_", " ", text)
    words = []
    for word in text.split():
        if re.fullmatch(r"ال[؀-ۿ]{2,}", word):
            word = word[2:]
        words.append(word)
    return " " + " ".join(w for w in _LATIN_NOISE.sub(" ", " ".join(words)).split()) + " "


@lru_cache(maxsize=1)
def _aliases() -> list[tuple[str, District]]:
    """Every alias as folded words, longest first: the most specific place named wins."""
    seen: dict[str, District] = {}
    for district in DISTRICTS:
        for alias in district.aliases:
            folded = fold(alias)
            if folded.strip() and folded not in seen:
                seen[folded] = district
    return sorted(seen.items(), key=lambda pair: -len(pair[0]))


def match(text: str | None, regions: set[str] | None = None, *, last: bool = False) -> District | None:
    """The place `text` names. `last`: a link's path runs from the city to the street, so the place
    named last is the most specific («…-new-cairo-madinaty-…» is Madinaty)."""
    folded = fold(text)
    if not folded.strip():
        return None
    found = [(folded.rfind(alias), len(alias), district) for alias, district in _aliases()
             if alias in folded and (regions is None or district.region in regions)]
    if not found:
        return None
    if last:
        return max(found, key=lambda item: (item[0] + item[1], item[1]))[2]
    return found[0][2]


def _url_words(url: str | None) -> str:
    """The location part of a listing link: «/en/listing/123-for-sale-cairo-new-cairo-el-narges/»."""
    if not url:
        return ""
    try:
        path = unquote(urlsplit(url).path)
    except ValueError:
        return ""
    return " ".join(part for part in re.split(r"[/_-]+", path) if not part.isdigit())


def resolve(district: str | None = None, compound: str | None = None, *, city: str | None = None,
            url: str | None = None, title: str | None = None) -> District | None:
    """The market district a listing is in, from the most specific evidence that names one."""
    regions = SCOPE_REGIONS.get((city or "").casefold())
    for text, last in ((district, False), (compound, False), (_url_words(url), True), (title, False)):
        found = match(text, regions, last=last)
        if found:
            return found
    fallback = SCOPE_FALLBACK.get((city or "").casefold())
    return BY_KEY[fallback] if fallback else None


def district_name(name: str | None) -> str | None:
    """A source's district spelling as the market district's name, or the spelling itself."""
    if not name:
        return None
    found = match(name)
    return found.name if found else " ".join(name.split())


def public(district: District) -> dict:
    return {"key": district.key, "name": district.name, "name_ar": district.name_ar, "region": district.region,
            "region_name": REGION_NAMES[district.region][0], "region_name_ar": REGION_NAMES[district.region][1],
            "lat": district.lat, "lon": district.lon, "in_compounds": district.in_compounds}
