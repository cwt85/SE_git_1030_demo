from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from DB import Database, get_database

router = APIRouter()
DB = Annotated[Database, Depends(get_database)]
EventStatus = Literal["open", "closed", "cancelled"]


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EventCreate(RequestBody):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    registration_deadline: AwareDatetime | None = None
    status: EventStatus = "open"

    @model_validator(mode="after")
    def valid_deadline(self):
        if self.registration_deadline is not None and self.registration_deadline <= datetime.now(timezone.utc):
            raise ValueError("報名截止時間必須晚於現在。")
        return self


class EventUpdate(RequestBody):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    registration_deadline: AwareDatetime | None = None
    status: EventStatus | None = None


class RegistrationCreate(RequestBody):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=60)


@router.get("/events")
def list_events(db: DB, status: EventStatus | None = None, only_open: bool = Query(default=False)):
    return db.list_events(status=status, only_open=only_open)


@router.get("/events/{event_id}")
def event_detail(event_id: int, db: DB):
    return db.get_event(event_id)


@router.post("/events/{event_id}/registrations", status_code=201)
def register(event_id: int, payload: RegistrationCreate, db: DB):
    return db.register(event_id, **payload.model_dump())


@router.get("/events/{event_id}/registrations")
def public_roster(event_id: int, db: DB):
    return db.list_registrations(event_id)


@router.post("/admin/events", status_code=201)
def create_event(payload: EventCreate, db: DB):
    return db.create_event(**payload.model_dump())


@router.patch("/admin/events/{event_id}")
def update_event(event_id: int, payload: EventUpdate, db: DB):
    changes = payload.model_dump(exclude_unset=True)
    if not changes or any(key in changes and changes[key] is None for key in ("title", "status")):
        raise HTTPException(status_code=422, detail="請提供有效的活動修改內容。")
    return db.update_event(event_id, **changes)


@router.get("/admin/events/{event_id}/registrations")
def admin_roster(event_id: int, db: DB):
    # Classroom/local scope, as specified in the agreed plan; no login in this version.
    return db.list_registrations(event_id, public=False)
