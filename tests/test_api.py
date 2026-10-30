from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from DB import get_database
from main import app


@pytest.fixture
def client(database):
    db, _ = database
    app.dependency_overrides[get_database] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_http_registration_flow(client):
    response = client.post("/api/v1/admin/events", json={"title": "API串接活動"})
    assert response.status_code == 201
    event = response.json()
    event_id = event["id"]
    assert event["registration_count"] == 0
    url = f"/api/v1/events/{event_id}/registrations"
    assert client.post(url, json={"name": "測試甲", "phone": "0912345678"}).status_code == 201
    assert client.post(url, json={"name": " 測試甲 ", "phone": "+886912345678"}).status_code == 409
    assert client.get(f"/api/v1/events/{event_id}").json()["registration_count"] == 1
    assert client.get("/api/v1/events").json()[0]["registration_count"] == 1
    assert client.get(url).json() == [{"name": "測試甲"}]
    assert client.get(f"/api/v1/admin/events/{event_id}/registrations").json()[0]["phone"] == "0912345678"
    assert client.patch(f"/api/v1/admin/events/{event_id}", json={"status": "closed"}).status_code == 200
    assert client.post(url, json={"name": "測試乙", "phone": "0000000002"}).status_code == 400
    assert client.get("/api/v1/events?only_open=true").json() == []


@pytest.mark.integration
def test_http_validation_deadline_and_templates(client):
    assert client.post("/api/v1/admin/events", json={"title": "   "}).status_code == 422
    assert client.post("/api/v1/admin/events", json={"title": "無時區", "starts_at": "2026-11-01T12:00:00"}).status_code == 422
    assert client.get("/api/v1/events/999999999").status_code == 404
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert client.post("/api/v1/admin/events", json={"title": "過期", "registration_deadline": expired}).status_code == 422
    event_id = client.post("/api/v1/admin/events", json={"title": "截止測試"}).json()["id"]
    assert client.patch(f"/api/v1/admin/events/{event_id}", json={"registration_deadline": expired}).status_code == 200
    assert client.post(f"/api/v1/events/{event_id}/registrations", json={"name": "測試", "phone": "0000000001"}).status_code == 400
    assert client.patch(f"/api/v1/admin/events/{event_id}", json={"title": None}).status_code == 422
    assert client.patch(f"/api/v1/admin/events/{event_id}", json={"status": None}).status_code == 422
    assert client.patch(f"/api/v1/admin/events/{event_id}", json={}).status_code == 422
    public = client.get("/")
    admin = client.get("/admin")
    assert public.status_code == admin.status_code == 200
    assert 'data-manage-mode="false"' in public.text
    assert 'data-manage-mode="true"' in admin.text
    assert 'data-action="create-event"' not in public.text
    assert 'data-action="create-event"' in admin.text
