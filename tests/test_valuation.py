"""Model building blocks: entity resolution, cash-equivalent pricing, calibration."""

from datetime import date

import pytest

from qayem.valuation import (
    canonical_district, delivery_bucket, developer_key, payment_terms, present_value_factor,
)


@pytest.mark.parametrize("names", [
    ("Palm Hills Developments", "Palm Hills", "Palm hills"),
    ("SODIC", "Sodic"),
    ("Mountain View", "Mountainview", "Mountain view"),
    ("Talaat Moustafa Group (TMG) Holding", "TMG", "Talaat Moustafa"),
    ("Emaar Misr", "Emaar"),
    ("Palm Hills Developments", "بالم هيلز"),
    ("IL Cazar Developments", "الكازار للتطوير العمراني-IL Cazar Developments", "الكازار"),
    ("Talaat Moustafa Group (TMG) Holding", "طلعت مصطفى"),
])
def test_developer_spellings_resolve_to_one_key(names):
    assert len({developer_key(name) for name in names}) == 1


def test_district_aliases():
    assert canonical_district("fifth settlement") == canonical_district("New Cairo") == "New Cairo"
    assert canonical_district("  Madinaty ") == "Madinaty"


def test_present_value_of_remaining_installments():
    assert present_value_factor(3) == pytest.approx(1 / 1.2 ** 0.25)
    assert 0.55 < present_value_factor(84) < 0.62  # seven years at 20%
    plan = payment_terms(10_000_000, 2_000_000, 84, True, cash_when_not_installment=False)
    assert plan["terms"] == "plan" and plan["remaining_share"] == 0.8
    assert plan["cash_equivalent"] == round(2_000_000 + 8_000_000 * present_value_factor(84))
    assert payment_terms(10_000_000, None, None, None, cash_when_not_installment=True)["cash_equivalent"] == 10_000_000
    assert payment_terms(10_000_000, None, None, None, cash_when_not_installment=False)["terms"] == "unknown"
    assert payment_terms(10_000_000, 2_000_000, None, True, cash_when_not_installment=True)["terms"] == "partial"


def test_delivery_buckets():
    today = date(2026, 9, 21)
    assert delivery_bucket("2025-12-31", None, today)[0] == "ready"
    assert delivery_bucket("2027-06-01", None, today)[0] == "under_1y"
    assert delivery_bucket("2031-01-01", None, today)[0] == "3y_plus"
    assert delivery_bucket(None, "ready_to_move", today) == ("ready", None)
    assert delivery_bucket(None, None, today) == ("unknown", None)


def test_payment_terms_uses_custom_discount_rate():
    low = payment_terms(10_000_000, 2_000_000, 84, True, cash_when_not_installment=False, rate=0.15)
    high = payment_terms(10_000_000, 2_000_000, 84, True, cash_when_not_installment=False, rate=0.25)
    assert high["cash_equivalent"] < low["cash_equivalent"]
    assert high["discount"] > low["discount"]


def test_compound_spelling_variants_join_their_compound():
    from collections import Counter

    from qayem.website_data import match_compound

    anchors = {"the-brooks", "aliva-mountain-view-mostakbal-city", "seashore", "seashore-hyde-park-north", "badya",
               "hyde-park-north-lagoons"}
    devs = {"the-brooks": Counter(pre=9), "aliva-mountain-view-mostakbal-city": Counter(mountainview=9),
            "seashore": Counter(hydepark=9), "seashore-hyde-park-north": Counter(hydepark=9), "badya": Counter(palmhills=9),
            "hyde-park-north-lagoons": Counter(hydepark=9)}
    assert match_compound("thebrooks", Counter(pre=1), anchors, devs) == "the-brooks"
    assert match_compound("aliva-city", Counter(mountainview=1), anchors, devs) == "aliva-mountain-view-mostakbal-city"
    assert match_compound("كمبوند-باديا", Counter(palmhills=1), anchors, devs) == "badya"
    assert match_compound("seashore-phase-2", Counter(hydepark=1), anchors, devs) == "seashore"
    # a different developer never matches, and an ambiguous word matches nothing
    assert match_compound("aliva-city", Counter(sodic=1), anchors, devs) is None
    assert match_compound("north-villas", Counter(hydepark=1), anchors, devs) is None
