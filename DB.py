"""PostgreSQL access for the classroom main.py / route / templates structure.

Routes call get_database().<method>(...) and translate DatabaseError to HTTP errors.
Importing this module never connects, creates tables, or inserts demo data.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String,
    Text, UniqueConstraint, URL, create_engine, func, or_, select, text,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="ck_events_title"),
        CheckConstraint("status IN ('open', 'closed', 'cancelled')", name="ck_events_status"),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at", name="ck_events_times"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp())


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "name", "phone", name="uq_registrations_event_name_phone"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_registrations_name"),
        CheckConstraint("length(btrim(phone)) > 0", name="ck_registrations_phone"),
        Index("ix_registrations_event_created", "event_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", name="fk_registrations_event", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatabaseError(Exception):
    status_code = 400


class EventNotFound(DatabaseError):
    status_code = 404


class RegistrationClosed(DatabaseError):
    status_code = 400


class DuplicateRegistration(DatabaseError):
    status_code = 409


class InvalidInput(DatabaseError):
    status_code = 422


def database_url() -> URL:
    """Build a URL without interpolating/printing credentials, including @ in passwords."""
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("請在本機 .env 設定 DB_PASSWORD，或以環境變數提供。")
    return URL.create(
        "postgresql+psycopg", username=os.getenv("DB_USER", "postgres"),
        password=password, host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")), database=os.getenv("DB_NAME", "event_registration"),
    )


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database(create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5}))


def _required_text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise InvalidInput(f"{label}必須是文字。")
    value = value.strip()
    if not value or len(value) > limit:
        raise InvalidInput(f"{label}必填，且不能超過 {limit} 個字元。")
    return value


def normalize_phone(value: str) -> str:
    value = _required_text(value, "電話", 60)
    value = re.sub(r"[\s()\-]", "", unicodedata.normalize("NFKC", value))
    if not re.fullmatch(r"\+?[0-9]{6,29}", value) or len(value) > 30:
        raise InvalidInput("電話需為 6 至 29 位數字，可含開頭的 +。")
    return value


EVENT_FIELDS = {"title", "description", "location", "starts_at", "ends_at", "registration_deadline", "status"}


def _validate_event(values: dict[str, Any]) -> dict[str, Any]:
    if set(values) - EVENT_FIELDS:
        raise InvalidInput("含有不允許修改的活動欄位。")
    values = dict(values)
    values["title"] = _required_text(values.get("title"), "活動名稱", 200)
    if values.get("status", "open") not in ("open", "closed", "cancelled"):
        raise InvalidInput("活動狀態必須是 open、closed 或 cancelled。")
    for key, limit in (("description", None), ("location", 255)):
        value = values.get(key)
        if value is not None:
            if not isinstance(value, str) or (limit and len(value) > limit):
                raise InvalidInput(f"{key} 格式或長度不正確。")
    for key in ("starts_at", "ends_at", "registration_deadline"):
        value = values.get(key)
        if value is not None and (
            not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None
        ):
            raise InvalidInput(f"{key} 必須是包含時區的 datetime。")
    start, end = values.get("starts_at"), values.get("ends_at")
    if start is not None and end is not None and end < start:
        raise InvalidInput("結束時間不能早於開始時間。")
    return values


class Database:
    """One short transaction per method. Connection binding is supported for rollback tests."""

    def __init__(self, bind: Engine | Connection):
        self.bind = bind

    def _session(self) -> Session:
        return Session(self.bind, expire_on_commit=False, join_transaction_mode="create_savepoint")

    @staticmethod
    def _find_event(session: Session, event_id: int, *, lock: bool = False) -> Event:
        query = select(Event).where(Event.id == event_id)
        if lock:
            query = query.with_for_update()
        event = session.scalar(query)
        if event is None:
            raise EventNotFound("找不到此活動。")
        return event

    @staticmethod
    def _event_dict(event: Event, count: int) -> dict[str, Any]:
        return {**{column.name: getattr(event, column.name) for column in Event.__table__.columns},
                "registration_count": int(count)}

    @staticmethod
    def _count(session: Session, event_id: int) -> int:
        return session.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == event_id)) or 0

    def create_event(self, **values: Any) -> dict[str, Any]:
        values = _validate_event(values)
        with self._session() as session, session.begin():
            event = Event(**values)
            session.add(event)
            session.flush()
            return self._event_dict(event, 0)

    def list_events(self, *, status: str | None = None, only_open: bool = False) -> list[dict[str, Any]]:
        if status is not None and status not in ("open", "closed", "cancelled"):
            raise InvalidInput("不支援的活動狀態。")
        counts = select(Registration.event_id, func.count().label("total")).group_by(Registration.event_id).subquery()
        query = select(Event, func.coalesce(counts.c.total, 0)).outerjoin(counts, Event.id == counts.c.event_id)
        if status is not None:
            query = query.where(Event.status == status)
        if only_open:
            query = query.where(Event.status == "open", or_(Event.registration_deadline.is_(None), Event.registration_deadline > func.statement_timestamp()))
        with self._session() as session:
            return [self._event_dict(event, count) for event, count in session.execute(query.order_by(Event.id.desc()))]

    def get_event(self, event_id: int) -> dict[str, Any]:
        with self._session() as session:
            event = self._find_event(session, event_id)
            return self._event_dict(event, self._count(session, event_id))

    def update_event(self, event_id: int, **changes: Any) -> dict[str, Any]:
        if set(changes) - EVENT_FIELDS:
            raise InvalidInput("含有不允許修改的活動欄位。")
        with self._session() as session, session.begin():
            event = self._find_event(session, event_id, lock=True)
            values = _validate_event({**{key: getattr(event, key) for key in EVENT_FIELDS}, **changes})
            for key in changes:
                setattr(event, key, values[key])
            session.flush()
            return self._event_dict(event, self._count(session, event_id))

    def register(self, event_id: int, *, name: str, phone: str) -> dict[str, Any]:
        name = _required_text(name, "姓名", 100)
        phone = normalize_phone(phone)
        try:
            with self._session() as session, session.begin():
                # Share the event row lock with update_event, including manual closure.
                event = self._find_event(session, event_id, lock=True)
                now = session.scalar(select(func.clock_timestamp()))
                if event.status != "open" or (event.registration_deadline is not None and now >= event.registration_deadline):
                    raise RegistrationClosed("此活動已停止報名或已超過截止時間。")
                record = Registration(event_id=event_id, name=name, phone=phone)
                session.add(record)
                session.flush()
                return {"id": record.id, "event_id": record.event_id, "name": record.name, "created_at": record.created_at}
        except IntegrityError as exc:
            if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_registrations_event_name_phone":
                raise DuplicateRegistration("此活動已存在相同姓名與電話的報名。") from exc
            raise

    def list_registrations(self, event_id: int, *, public: bool = True) -> list[dict[str, Any]]:
        with self._session() as session:
            self._find_event(session, event_id)
            records = session.scalars(select(Registration).where(Registration.event_id == event_id).order_by(Registration.created_at, Registration.id))
            if public:
                return [{"name": record.name} for record in records]
            return [{column.name: getattr(record, column.name) for column in Registration.__table__.columns} for record in records]
