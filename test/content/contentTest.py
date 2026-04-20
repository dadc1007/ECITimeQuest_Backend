from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.database import get_db
from app.modules.content import service
from app.modules.content.router import router

PERIOD_NAME = "Edad Media"
TOPIC_NAME = "Cruzadas"
TOPIC_DESCRIPTION = "Campanas militares"
ADMIN_LOOKUP_PATH = "app.modules.content.router.get_user_by_firebase_uid"


def _period_payload() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "name": PERIOD_NAME,
        "description": "Periodo historico",
        "start_year": 500,
        "end_year": 1500,
        "order": 1,
        "is_active": True,
        "is_published": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def _admin_user_payload() -> dict:
    return {
        "id": str(uuid4()),
        "firebase_uid": "firebase-test-uid",
        "email": "user@example.com",
        "name": "Admin Test",
        "role": "admin",
    }


def _topic_payload(period_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "period_id": period_id or str(uuid4()),
        "name": TOPIC_NAME,
        "description": TOPIC_DESCRIPTION,
        "difficulty": 4,
        "difficulty_hint": "Relaciona causas y consecuencias",
        "order": 2,
        "is_premium": False,
        "is_active": True,
        "is_published": True,
        "xp_reward": 60,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def _event_payload() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "name": "Caida de Constantinopla",
        "description": "Evento clave",
        "year": 1453,
        "era_start_year": None,
        "era_end_year": None,
        "location": "Constantinopla",
        "difficulty_hint": "Analiza impacto politico",
        "is_published": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def _figure_payload() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "name": "Juana de Arco",
        "role": "Lider militar",
        "biography": "Figura relevante",
        "birth_year": 1412,
        "death_year": 1431,
        "difficulty_hint": "Ubica su rol en la guerra",
        "is_published": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def _challenge_payload(topic_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "topic_id": topic_id or str(uuid4()),
        "title": "Reto cronologico",
        "description": "Ordena eventos en tiempo",
        "xp_reward": 100,
        "coin_reward": 50,
        "required_score": 80,
        "is_premium": False,
        "is_active": True,
        "is_published": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def _ai_context_payload(topic_id: str) -> dict:
    return {
        "topic_id": topic_id,
        "topic_name": TOPIC_NAME,
        "topic_description": "Contexto base",
        "difficulty": 4,
        "difficulty_hint": "Relaciona actores y consecuencias",
        "period_name": "Edad Media",
        "events": [_event_payload()],
        "figures": [_figure_payload()],
    }


@pytest.fixture
def app_client() -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)

    def fake_get_db():
        yield MagicMock()

    def fake_current_user():
        return {"uid": "firebase-test-uid", "email": "user@example.com", "role": "admin"}

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[get_current_user] = fake_current_user
    return TestClient(app)


@pytest.fixture
def app_client_without_email() -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)

    def fake_get_db():
        yield MagicMock()

    def fake_current_user():
        return {"uid": "firebase-test-uid"}

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[get_current_user] = fake_current_user
    return TestClient(app)


@pytest.fixture
def raw_client() -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)

    def fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_get_db
    return TestClient(app)


def test_list_periods_success(app_client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "get_all_periods", lambda db, only_published, skip, limit: [_period_payload()])

    response = app_client.get("/content/periods")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == PERIOD_NAME


def test_get_period_not_found_returns_404(app_client: TestClient, monkeypatch):
    def _raise_not_found(db, period_id):
        raise HTTPException(status_code=404, detail="Period not found")

    monkeypatch.setattr(service, "get_period_by_id", _raise_not_found)

    response = app_client.get(f"/content/periods/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Period not found"


def test_create_period_uses_uid_when_email_missing(app_client_without_email: TestClient, monkeypatch):
    captured = {}

    def _create_period(db, data, updated_by):
        captured["updated_by"] = updated_by
        return _period_payload()

    monkeypatch.setattr(service, "create_period", _create_period)
    monkeypatch.setattr(ADMIN_LOOKUP_PATH, lambda db, uid: _admin_user_payload())

    response = app_client_without_email.post(
        "/content/periods",
        json={
            "name": "Edad Moderna",
            "description": "Periodo moderno",
            "start_year": 1500,
            "end_year": 1800,
            "order": 2,
        },
    )

    assert response.status_code == 201
    assert captured["updated_by"] == "firebase-test-uid"


def test_create_topic_conflict_returns_409(app_client: TestClient, monkeypatch):
    def _raise_conflict(db, data, updated_by):
        raise HTTPException(status_code=409, detail="A topic with this name already exists in this period")

    monkeypatch.setattr(service, "create_topic", _raise_conflict)
    monkeypatch.setattr(ADMIN_LOOKUP_PATH, lambda db, uid: _admin_user_payload())

    response = app_client.post(
        "/content/topics",
        json={
            "period_id": str(uuid4()),
            "name": "Cruzadas",
            "description": TOPIC_DESCRIPTION,
            "difficulty": 4,
            "order": 1,
            "xp_reward": 50,
            "is_premium": False,
        },
    )

    assert response.status_code == 409


def test_create_topic_requires_admin_role(app_client_without_email: TestClient, monkeypatch):
    monkeypatch.setattr(ADMIN_LOOKUP_PATH, lambda db, uid: None)

    response = app_client_without_email.post(
        "/content/topics",
        json={
            "period_id": str(uuid4()),
            "name": "Cruzadas",
            "description": TOPIC_DESCRIPTION,
            "difficulty": 4,
            "order": 1,
            "xp_reward": 50,
            "is_premium": False,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_get_event_success(app_client: TestClient, monkeypatch):
    event_payload = _event_payload()

    monkeypatch.setattr(service, "get_event_by_id", lambda db, event_id: event_payload)

    response = app_client.get(f"/content/events/{event_payload['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Caida de Constantinopla"


def test_link_event_to_topic_returns_204(app_client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "add_event_to_topic", lambda db, topic_id, event_id: None)
    monkeypatch.setattr(ADMIN_LOOKUP_PATH, lambda db, uid: _admin_user_payload())

    response = app_client.post(f"/content/topics/{uuid4()}/events/{uuid4()}")

    assert response.status_code == 204
    assert response.text == ""


def test_get_figure_success(app_client: TestClient, monkeypatch):
    figure_payload = _figure_payload()

    monkeypatch.setattr(service, "get_figure_by_id", lambda db, figure_id: figure_payload)

    response = app_client.get(f"/content/figures/{figure_payload['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Juana de Arco"


def test_get_challenge_success(app_client: TestClient, monkeypatch):
    challenge_payload = _challenge_payload()

    monkeypatch.setattr(service, "get_challenge_by_id", lambda db, challenge_id: challenge_payload)

    response = app_client.get(f"/content/challenges/{challenge_payload['id']}")

    assert response.status_code == 200
    assert response.json()["title"] == "Reto cronologico"


def test_get_ai_context_success(app_client: TestClient, monkeypatch):
    topic_id = str(uuid4())

    monkeypatch.setattr(service, "get_topic_context_for_ai", lambda db, t_id: _ai_context_payload(topic_id))

    response = app_client.get(f"/content/topics/{topic_id}/ai-context")

    assert response.status_code == 200
    assert response.json()["topic_name"] == TOPIC_NAME
    assert len(response.json()["events"]) == 1
    assert len(response.json()["figures"]) == 1


def test_get_period_without_token_returns_403(raw_client: TestClient):
    response = raw_client.get(f"/content/periods/{uuid4()}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not authenticated"


def test_get_period_with_invalid_token_returns_401(raw_client: TestClient, monkeypatch):
    monkeypatch.setattr("app.core.security.verify_firebase_token", lambda token: None)

    response = raw_client.get(
        f"/content/periods/{uuid4()}",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"
