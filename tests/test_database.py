from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from DB import (DuplicateRegistration, EventNotFound, InvalidInput,
                RegistrationClosed, normalize_phone)


@pytest.mark.parametrize("raw, expected", [
    ("0912-345-678", "0912345678"),
    (" ０９１２ ３４５ ６７８ ", "0912345678"),
    ("+886 (912) 345-678", "0912345678"),
    ("886912345678", "0912345678"),
    ("+1 (202) 555-0100", "+12025550100"),
])
def test_phone_normalization(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("value", [None, "", "abc", "123", "0912; DROP TABLE events", "1" * 31])
def test_reject_bad_phones(value):
    with pytest.raises(InvalidInput):
        normalize_phone(value)


@pytest.mark.integration
def test_activity_registration_count_and_rosters(database):
    db, _ = database
    event = db.create_event(title="測試活動")
    assert event["registration_count"] == 0
    result = db.register(event["id"], name=" 測試甲 ", phone="0912-345-678")
    assert result["name"] == "測試甲" and "phone" not in result
    assert db.get_event(event["id"])["registration_count"] == 1
    assert db.list_events()[0]["registration_count"] == 1
    assert db.list_registrations(event["id"]) == [{"name": "測試甲"}]
    assert db.list_registrations(event["id"], public=False)[0]["phone"] == "0912345678"


@pytest.mark.integration
def test_duplicates_and_recovery(database):
    db, _ = database
    first = db.create_event(title="活動甲")["id"]
    second = db.create_event(title="活動乙")["id"]
    db.register(first, name="測試甲", phone="0912345678")
    with pytest.raises(DuplicateRegistration):
        db.register(first, name=" 測試甲 ", phone="０９１２-３４５-６７８")
    with pytest.raises(DuplicateRegistration):
        db.register(first, name="測試甲", phone="+886912345678")
    db.register(second, name="測試甲", phone="0912345678")
    db.register(first, name="測試乙", phone="0912345678")
    db.register(first, name="測試甲", phone="0987654321")
    assert db.get_event(first)["registration_count"] == 3
    assert db.get_event(second)["registration_count"] == 1


@pytest.mark.integration
@pytest.mark.parametrize("status", ["closed", "cancelled"])
def test_manual_closure(database, status):
    db, connection = database
    event = db.create_event(title="關閉測試")
    before = event["updated_at"]
    changed = db.update_event(event["id"], status=status)
    assert changed["updated_at"] >= before
    with pytest.raises(RegistrationClosed):
        db.register(event["id"], name="測試甲", phone="0000000001")
    assert db.list_events(only_open=True) == []
    assert connection.scalar(text("SELECT count(*) FROM registrations")) == 0


@pytest.mark.integration
def test_deadline_and_listing(database):
    db, connection = database
    now = connection.scalar(select(func.clock_timestamp()))
    expired = db.create_event(title="已截止", registration_deadline=now - timedelta(seconds=1))
    future = db.create_event(title="尚未截止", registration_deadline=now + timedelta(hours=1))
    unlimited = db.create_event(title="不限截止")
    with pytest.raises(RegistrationClosed):
        db.register(expired["id"], name="測試甲", phone="0000000001")
    db.register(future["id"], name="測試甲", phone="0000000001")
    assert {e["id"] for e in db.list_events(only_open=True)} == {future["id"], unlimited["id"]}
    # status=open alone is an administrative status filter, not a deadline filter.
    assert len(db.list_events(status="open")) == 3


@pytest.mark.integration
def test_database_constraints_even_without_python_validation(database):
    db, connection = database
    event = db.create_event(title="資料庫限制")
    db.register(event["id"], name="測試甲", phone="0000000001")
    invalid_statements = [
        ("INSERT INTO registrations(event_id,name,phone) VALUES (:id,'測試甲','0000000001')", "uq_registrations_event_name_phone"),
        ("INSERT INTO registrations(event_id,name,phone) VALUES (-1,'測試甲','0000000001')", "fk_registrations_event"),
        ("DELETE FROM events WHERE id=:id", "fk_registrations_event"),
        ("INSERT INTO events(title,status) VALUES ('測試','unknown')", "ck_events_status"),
        ("INSERT INTO events(title) VALUES ('   ')", "ck_events_title"),
    ]
    for statement, constraint in invalid_statements:
        with pytest.raises(IntegrityError) as error:
            with connection.begin_nested():
                connection.execute(text(statement), {"id": event["id"]})
        assert error.value.orig.diag.constraint_name == constraint


@pytest.mark.integration
def test_missing_events_and_time_validation(database):
    db, _ = database
    for action in (lambda: db.get_event(-1), lambda: db.update_event(-1, status="closed"),
                   lambda: db.list_registrations(-1), lambda: db.register(-1, name="測試", phone="0000000001")):
        with pytest.raises(EventNotFound):
            action()
    with pytest.raises(InvalidInput):
        db.create_event(title="無時區", starts_at=datetime(2026, 11, 1))
    now = datetime.now(timezone.utc)
    with pytest.raises(InvalidInput):
        db.create_event(title="時間反向", starts_at=now, ends_at=now - timedelta(hours=1))
    event = db.create_event(title="正常活動", starts_at=now, ends_at=now + timedelta(hours=1))
    with pytest.raises(InvalidInput):
        db.update_event(event["id"], starts_at=now + timedelta(hours=2))
    assert db.get_event(event["id"])["starts_at"] == now


@pytest.mark.integration
def test_sql_input_is_stored_as_data(database):
    db, _ = database
    title = "Robert'); DROP TABLE events; --"
    event = db.create_event(title=title)
    assert db.get_event(event["id"])["title"] == title
    assert len(db.list_events()) == 1
