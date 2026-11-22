"""No personal data from sources is stored: parsed listings, stored rows and their history."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from qayem.db import init_db
from qayem.models import Property, PropertyVersion
from qayem.privacy import scrub_raw, scrub_text
from qayem.sources.base import NormalizedListing
from qayem.upsert import scrub_stored, upsert_listing


def test_contacts_are_removed_from_text_and_payloads():
    assert scrub_text("اتصل 0101 234 5678 أو a.b@x.com") == "اتصل [contact withheld] أو [contact withheld]"
    assert scrub_text("price 15,000,000 EGP, 3 bedrooms") == "price 15,000,000 EGP, 3 bedrooms"
    raw = {"id": 7, "member_display_name": "Ahmed", "phone_number": "0100", "phone_reveal_key": "k",
           "shop_name": "Home", "masked_description": "call 01012345678", "units_obj": {"contact": "x", "Surface": 1}}
    assert scrub_raw(raw) == {"id": 7, "masked_description": "call [contact withheld]", "units_obj": {"Surface": 1}}


def test_upsert_never_stores_contacts_and_scrub_cleans_old_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'q.db'}")
    init_db(engine)
    with Session(engine) as session:
        listing = NormalizedListing(source_listing_id="1", title="Villa, call 01012345678",
                                    raw={"member_user_name": "seller1", "price_amount": 5})
        upsert_listing(session, "opensooq", listing)
        session.flush()
        prop = session.execute(select(Property)).scalar_one()
        assert prop.title == "Villa, call [contact withheld]" and prop.raw == {"price_amount": 5}
        # A row an earlier crawl stored with a phone, and its history.
        old = Property(source="gpm", source_listing_id="2", status="active", phone="+201070399500",
                       description="WhatsApp 01070399500", raw={"seller": "Mr X"})
        session.add(old)
        session.flush()
        session.add(PropertyVersion(property_id=old.id, change_type="updated",
                                    payload={"phone": "+201070399500", "price": 1},
                                    changed_fields={"phone": {"old": None, "new": "+201070399500"},
                                                    "description": {"old": "x", "new": "WhatsApp 01070399500"}}))
        session.commit()
        assert scrub_stored(session)["versions"] >= 1
        session.commit()
        old = session.get(Property, old.id)
        assert old.phone is None and old.raw == {} and "0107" not in old.description
        texts = [str((v.payload, v.changed_fields)) for v in session.execute(select(PropertyVersion)).scalars()]
        assert not any("0107" in text or "seller1" in text for text in texts)
        assert scrub_stored(session) == {"properties": 0, "versions": 0}
