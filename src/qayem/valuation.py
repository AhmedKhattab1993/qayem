"""Fair-value model for Egyptian resale units.

Price per m² is modelled in log space on a *cash-equivalent* basis: a unit
sold on a seven-year plan is not comparable to a cash unit until its
remaining installments are discounted to today's money.

    log(cash EGP/m²) = class baseline
                     + district effect
                     + developer-in-district effect
                     + compound effect
                     + unit type + finishing + delivery + size adjustments

Each location/brand level is a shrunken mean of residuals from the level
above (empirical-Bayes style: a compound with 3 listings moves only part of
the way from its developer's norm). Unit adjustments are fitted jointly by
backfitting. Accuracy is measured by leave-one-out backtest, and the
published range for each confidence grade is the backtest's own 10th–90th
percentile error, so ranges are calibrated rather than asserted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
import math
import re
from statistics import median
from typing import Iterable

DISCOUNT_RATE = 0.20  # annual, applied to remaining installments
PAYMENT_INTERVAL_MONTHS = 3  # plans are modelled as equal quarterly payments
SHRINK = 4.0  # pseudo-listings pulling each location level towards its parent
SHRINK_ADJUSTMENT = 25.0
RESIDUAL_CLIP = 0.6  # log units; limits one mispriced listing's pull on its group
OUTLIER_LOG = math.log(2.5)
ITERATIONS = 5
MIN_CALIBRATION = 50  # backtest errors needed before a grade's range comes from data
DEFAULT_BAND = (math.log(0.75), math.log(1.25))
MIN_BAND = math.log(1.10)  # a range is never narrower than ±10%

CLASSES = {
    "apartment": "apartment", "studio": "apartment", "duplex": "apartment",
    "penthouse": "apartment", "loft": "apartment", "roof": "apartment",
    "chalet": "chalet", "cabin": "chalet",
    "villa": "house", "townhouse": "house", "twinhouse": "house",
    "house": "house", "family house": "house",
}
REFERENCE_TYPE = {"apartment": "apartment", "chalet": "chalet", "house": "villa"}
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
                  installments: bool | None, cash_when_not_installment: bool) -> dict:
    """Classify the payment structure and derive today's-money cost where terms are known.

    terms: 'cash' | 'plan' | 'partial' (installments, term unknown) | 'unknown'.
    """
    if installments and down_payment is not None and months:
        remaining = max(0.0, price - down_payment)
        present = down_payment + remaining * present_value_factor(months)
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


@dataclass
class Unit:
    """One unit reduced to the model's inputs."""

    id: int | None
    cls: str
    type: str
    district: str
    developer: str
    compound: str
    finishing: str
    delivery: str
    log_area: float
    y: float | None = None  # log cash-equivalent EGP/m²; None when terms are unknown
    plan: str = "cash"
    in_compound: bool | None = None  # None: inferred from `compound`

    def keys(self) -> list[tuple]:
        # Compound and non-compound stock price differently even in one district,
        # so each has its own district benchmark.
        gated = bool(self.compound) if self.in_compound is None else self.in_compound
        path: list[tuple] = [("class", self.cls), ("district", self.cls, self.district.casefold(), gated)]
        if self.developer:
            path.append(("developer", self.cls, self.district.casefold(), self.developer))
        if self.compound:
            path.append(("compound", self.cls, self.compound))
        return path


GRADE_RULES = (
    ("A", "compound", 6),
    ("B", "compound", 2),
    ("B", "developer", 6),
    ("C", "district", 6),
)


@dataclass
class Model:
    reference_date: date
    stats: dict[tuple, list[float]] = field(default_factory=dict)  # key → [residual sum, n]
    base: dict[str, float] = field(default_factory=dict)
    effects: dict[str, dict[str, float]] = field(default_factory=dict)
    area_center: dict[str, float] = field(default_factory=dict)
    area_slope: dict[str, float] = field(default_factory=dict)
    calibration: dict[str, dict] = field(default_factory=dict)
    contributions: dict[int, list[float]] = field(default_factory=dict)  # unit id → own residual per level
    backtest: dict = field(default_factory=dict)

    # --- prediction ---------------------------------------------------------

    def adjustment(self, unit: Unit) -> float:
        return (self.effects["type"].get(unit.type, 0.0) + self.effects["finishing"].get(unit.finishing, 0.0)
                + self.effects["delivery"].get(unit.delivery, 0.0) + self.effects["plan"].get(unit.plan, 0.0)
                + self.area_slope.get(unit.cls, 0.0) * (unit.log_area - self.area_center.get(unit.cls, unit.log_area)))

    def path(self, unit: Unit, exclude: bool = False) -> list[dict]:
        """The location/brand estimate level by level. `exclude` removes the unit's own listing (LOO)."""
        if unit.cls not in self.base:
            return []
        own = self.contributions.get(unit.id, []) if exclude and unit.id is not None else []
        estimate = self.base[unit.cls]
        steps = [{"level": "class", "n": int(self.stats.get(("class", unit.cls), [0, 0])[1]), "delta": 0.0,
                  "estimate": estimate}]
        for depth, key in enumerate(unit.keys()[1:], start=1):
            total, count = self.stats.get(key, (0.0, 0))
            if exclude and depth < len(own) and count:
                total, count = total - own[depth], count - 1
            delta = total / (count + SHRINK) if count else 0.0
            estimate += delta
            steps.append({"level": key[0], "n": int(count), "delta": delta, "estimate": estimate})
        return steps

    def grade(self, steps: list[dict]) -> str | None:
        counts = {step["level"]: step["n"] for step in steps}
        for grade, level, minimum in GRADE_RULES:
            if counts.get(level, 0) >= minimum:
                return grade
        return None

    def predict(self, unit: Unit, exclude: bool = False) -> dict | None:
        steps = self.path(unit, exclude)
        grade = self.grade(steps)
        if grade is None:
            return None
        log_fair = steps[-1]["estimate"] + self.adjustment(unit)
        band = self.calibration.get(grade)
        low, high = (band["low"], band["high"]) if band else DEFAULT_BAND
        return {"grade": grade, "log_fair": log_fair, "fair_ppm": math.exp(log_fair),
                "low_ppm": math.exp(log_fair + low), "high_ppm": math.exp(log_fair + high), "steps": steps}

    def reference(self, unit: Unit) -> float | None:
        """Location/brand estimate alone: a finished, ready, reference-type unit of typical size."""
        steps = self.path(unit)
        return math.exp(steps[-1]["estimate"]) if steps else None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _clip(value: float) -> float:
    return max(-RESIDUAL_CLIP, min(RESIDUAL_CLIP, value))


def drop_outliers(units: list[Unit]) -> list[Unit]:
    """Remove listings priced implausibly far from their district (typos, per-m² prices typed as totals)."""
    groups: dict[tuple, list[float]] = defaultdict(list)
    for unit in units:
        groups[(unit.cls, unit.district.casefold())].append(unit.y)
        groups[(unit.cls,)].append(unit.y)
    centers = {key: median(values) for key, values in groups.items() if len(values) >= 5}
    kept = []
    for unit in units:
        center = centers.get((unit.cls, unit.district.casefold()), centers.get((unit.cls,)))
        if center is None or abs(unit.y - center) <= OUTLIER_LOG:
            kept.append(unit)
    return kept


def fit(units: Iterable[Unit], reference_date: date) -> Model:
    units = drop_outliers([unit for unit in units if unit.y is not None and unit.cls in REFERENCE_TYPE])
    model = Model(reference_date=reference_date)
    model.effects = {"type": {}, "finishing": {}, "delivery": {}, "plan": {}}
    by_class: dict[str, list[Unit]] = defaultdict(list)
    for unit in units:
        by_class[unit.cls].append(unit)
    model.area_center = {cls: median(u.log_area for u in group) for cls, group in by_class.items()}
    hierarchy: dict[int, float] = {}
    for _ in range(ITERATIONS):
        # 1. location/brand levels on adjusted prices
        adjusted = {id(u): u.y - model.adjustment(u) for u in units}
        model.base = {cls: _mean([adjusted[id(u)] for u in group]) for cls, group in by_class.items()}
        model.stats = {("class", cls): [0.0, float(len(group))] for cls, group in by_class.items()}
        estimate = {id(u): model.base[u.cls] for u in units}
        contributions: dict[int, list[float]] = {id(u): [0.0] for u in units}
        for depth in (1, 2, 3):
            level_units = [u for u in units if len(u.keys()) > depth]
            sums: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0])
            for unit in level_units:
                key = unit.keys()[depth]
                residual = _clip(adjusted[id(unit)] - estimate[id(unit)])
                contributions[id(unit)].append(residual)
                sums[key][0] += residual
                sums[key][1] += 1
            for unit in level_units:
                total, count = sums[unit.keys()[depth]]
                estimate[id(unit)] += total / (count + SHRINK)
            model.stats.update({key: [total, float(count)] for key, (total, count) in sums.items()})
        hierarchy = estimate
        model.contributions = {u.id: contributions[id(u)] for u in units if u.id is not None}
        # 2. unit adjustments on what the hierarchy leaves unexplained
        for factor, reference in (("type", None), ("finishing", "finished"), ("delivery", "ready"), ("plan", "cash")):
            groups: dict[str, list[float]] = defaultdict(list)
            for unit in units:
                others = model.adjustment(unit) - model.effects[factor].get(getattr(unit, factor), 0.0)
                groups[getattr(unit, factor)].append(unit.y - hierarchy[id(unit)] - others)
            effects = {level: sum(values) / (len(values) + SHRINK_ADJUSTMENT) for level, values in groups.items()}
            if factor == "type":
                for cls in by_class:
                    anchor = effects.get(REFERENCE_TYPE[cls], 0.0)
                    effects.update({kind: value - anchor for kind, value in effects.items()
                                    if CLASSES.get(kind) == cls})
            else:
                anchor = effects.get(reference, 0.0)
                effects = {level: value - anchor for level, value in effects.items()}
            model.effects[factor] = effects
        for cls, group in by_class.items():
            xs = [u.log_area - model.area_center[cls] for u in group]
            rs = [u.y - hierarchy[id(u)] - (model.adjustment(u) - model.area_slope.get(cls, 0.0) * x)
                  for u, x in zip(group, xs)]
            variance = sum(x * x for x in xs)
            model.area_slope[cls] = max(-0.8, min(0.3, sum(x * r for x, r in zip(xs, rs)) / variance)) if variance else 0.0
    model.backtest = backtest(model, units)
    return model


def backtest(model: Model, units: list[Unit]) -> dict:
    """Leave-one-out: each listing is valued as if it were not in the data."""
    errors: dict[str, list[float]] = defaultdict(list)
    naive: list[float] = []
    naive_groups: dict[tuple, list[float]] = defaultdict(list)
    for unit in units:
        naive_groups[(unit.cls, unit.district.casefold())].append(unit.y)
    naive_sorted = {key: sorted(values) for key, values in naive_groups.items()}
    paired_model: list[float] = []
    for unit in units:
        prediction = model.predict(unit, exclude=True)
        if prediction is None:
            continue
        error = unit.y - prediction["log_fair"]
        errors[prediction["grade"]].append(error)
        others = list(naive_sorted[(unit.cls, unit.district.casefold())])
        others.remove(unit.y)
        if len(others) >= 5:
            naive.append(abs(math.exp(unit.y - median(others)) - 1))
            paired_model.append(abs(math.exp(error) - 1))
    for grade, values in errors.items():
        low, high = ((_quantile(values, 0.10), _quantile(values, 0.90)) if len(values) >= MIN_CALIBRATION
                     else DEFAULT_BAND)
        model.calibration[grade] = {"low": min(low, -MIN_BAND), "high": max(high, MIN_BAND),
                                    "calibrated": len(values) >= MIN_CALIBRATION}
    grades = []
    for grade in ("A", "B", "C"):
        values = errors.get(grade, [])
        if not values:
            continue
        absolute = [abs(math.exp(v) - 1) for v in values]
        low, high = model.calibration[grade]["low"], model.calibration[grade]["high"]
        grades.append({"grade": grade, "count": len(values),
                       "median_abs_error": round(median(absolute), 4),
                       "within_10pct": round(sum(a <= 0.10 for a in absolute) / len(absolute), 4),
                       "within_20pct": round(sum(a <= 0.20 for a in absolute) / len(absolute), 4),
                       "range_low_pct": round(math.exp(low) - 1, 4), "range_high_pct": round(math.exp(high) - 1, 4),
                       "calibrated": model.calibration[grade]["calibrated"]})
    everything = [abs(math.exp(v) - 1) for values in errors.values() for v in values]
    return {
        "method": "leave-one-out",
        "trained_on": len(units),
        "evaluated": len(everything),
        "median_abs_error": round(median(everything), 4) if everything else None,
        "within_10pct": round(sum(a <= 0.10 for a in everything) / len(everything), 4) if everything else None,
        "within_20pct": round(sum(a <= 0.20 for a in everything) / len(everything), 4) if everything else None,
        "grades": grades,
        "naive_baseline": {
            "description": "Median price per m² of the same property class in the same district",
            "evaluated": len(naive),
            "median_abs_error": round(median(naive), 4) if naive else None,
            "model_median_abs_error": round(median(paired_model), 4) if paired_model else None,
        },
    }


def summarize_effects(model: Model) -> dict:
    """Fitted unit adjustments as percentage premiums, for publication."""
    def pct(value: float) -> float:
        return round(math.exp(value) - 1, 4)
    return {
        "type": {kind: pct(v) for kind, v in sorted(model.effects["type"].items())},
        "finishing": {level: pct(v) for level, v in model.effects["finishing"].items()},
        "delivery": {bucket: pct(model.effects["delivery"][bucket])
                     for bucket in DELIVERY_BUCKETS if bucket in model.effects["delivery"]},
        "plan": {bucket: pct(model.effects["plan"][bucket])
                 for bucket in PLAN_BUCKETS if bucket in model.effects["plan"]},
        "area_doubling": {cls: pct(slope * math.log(2)) for cls, slope in model.area_slope.items()},
        "discount_rate": DISCOUNT_RATE,
        "shrinkage": SHRINK,
    }


def majority(values: Iterable[str | None]) -> str | None:
    counted = Counter(value for value in values if value)
    return counted.most_common(1)[0][0] if counted else None
