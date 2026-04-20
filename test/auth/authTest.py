from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.rate_limit import limiter
from app.database import get_db
from app.core.security import get_current_user
from app.modules.auth.router import router
from app.modules.auth.schemas import UserCreate
from app.modules.auth import service


@pytest.fixture

def app_client() -> TestClient:
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


def _sample_user(firebase_uid: str = "firebase-test-uid", email: str = "user@example.com") -> dict:
	return {
		"id": str(uuid4()),
		"firebase_uid": firebase_uid,
		"email": email,
		"name": "Test User",
		"role": "user",
		"subscription_plan": "free",
		"created_at": datetime.now(timezone.utc).isoformat(),
	}


def test_sync_user_success(app_client: TestClient, monkeypatch):
	monkeypatch.setattr(service, "upsert_user_from_token", lambda db, token_payload: _sample_user())
	response = app_client.post("/auth/sync")

	assert response.status_code == 200
	assert response.json()["email"] == "user@example.com"


def test_sync_user_invalid_payload_returns_400(app_client: TestClient, monkeypatch):
	def _raise_invalid_payload(db, token_payload):
		raise HTTPException(status_code=400, detail="Token payload missing uid or email")

	monkeypatch.setattr(service, "upsert_user_from_token", _raise_invalid_payload)
	response = app_client.post("/auth/sync")

	assert response.status_code == 400
	assert response.json()["detail"] == "Token payload missing uid or email"


def test_get_me_success(app_client: TestClient, monkeypatch):
	monkeypatch.setattr(service, "get_user_by_firebase_uid", lambda db, uid: _sample_user())
	response = app_client.get("/auth/me")

	assert response.status_code == 200
	assert response.json()["subscription_plan"] == "free"


def test_get_me_user_not_found(app_client: TestClient, monkeypatch):
	monkeypatch.setattr(service, "get_user_by_firebase_uid", lambda db, uid: None)
	response = app_client.get("/auth/me")

	assert response.status_code == 404
	assert response.json()["detail"] == "User not found. Call /auth/sync first."


def test_create_user_conflict_by_email():
	db = MagicMock()
	db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate key value violates unique constraint users_email_key"))

	with pytest.raises(HTTPException) as exc_info:
		service.create_user(
			db,
			UserCreate(
				firebase_uid="firebase-test-uid",
				email="user@example.com",
				name="Test User",
				subscription_plan="free",
			),
		)

	assert exc_info.value.status_code == 409
	assert exc_info.value.detail == "Email already registered"
	db.rollback.assert_called_once()


def test_create_user_conflict_by_firebase_uid():
	db = MagicMock()
	db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate key value violates unique constraint users_firebase_uid_key"))

	with pytest.raises(HTTPException) as exc_info:
		service.create_user(
			db,
			UserCreate(
				firebase_uid="firebase-test-uid",
				email="user@example.com",
				name="Test User",
				subscription_plan="free",
			),
		)

	assert exc_info.value.status_code == 409
	assert exc_info.value.detail == "Firebase UID already registered"
	db.rollback.assert_called_once()


def test_upsert_user_from_token_reconciles_existing_email(monkeypatch):
	db = MagicMock()
	existing = SimpleNamespace(
		id=uuid4(),
		firebase_uid="old-firebase-uid",
		email="user@example.com",
		name="Old Name",
	)

	monkeypatch.setattr(service, "get_user_by_firebase_uid", lambda db, uid: None)
	monkeypatch.setattr(service, "get_user_by_email", lambda db, email: existing)

	result = service.upsert_user_from_token(
		db,
		{
			"uid": "new-firebase-uid",
			"email": "user@example.com",
			"name": "New Name",
		},
	)

	assert result.firebase_uid == "new-firebase-uid"
	assert result.name == "New Name"
	db.commit.assert_called_once()
	db.refresh.assert_called_once_with(existing)


def test_upsert_user_from_token_does_not_demote_admin_when_role_missing(monkeypatch):
	db = MagicMock()
	existing = SimpleNamespace(
		id=uuid4(),
		firebase_uid="firebase-test-uid",
		email="user@example.com",
		name="Admin User",
		role="admin",
	)

	monkeypatch.setattr(service, "get_user_by_firebase_uid", lambda db, uid: existing)

	result = service.upsert_user_from_token(
		db,
		{
			"uid": "firebase-test-uid",
			"email": "user@example.com",
			"name": "Admin User",
		},
	)

	assert result.role == "admin"
	db.commit.assert_not_called()


def test_get_me_without_token_returns_403(raw_client: TestClient):
	response = raw_client.get("/auth/me")

	assert response.status_code == 403
	assert response.json()["detail"] == "Not authenticated"


def test_get_me_with_invalid_token_returns_401(raw_client: TestClient, monkeypatch):
	monkeypatch.setattr("app.core.security.verify_firebase_token", lambda token: None)

	response = raw_client.get(
		"/auth/me",
		headers={"Authorization": "Bearer invalid-token"},
	)

	assert response.status_code == 401
	assert response.json()["detail"] == "Invalid or expired token"


def test_sync_rate_limit_returns_429(app_client: TestClient, monkeypatch):
	monkeypatch.setattr(service, "upsert_user_from_token", lambda db, token_payload: _sample_user())

	last_status = None
	for _ in range(20):
		response = app_client.post("/auth/sync")
		last_status = response.status_code
		if response.status_code == 429:
			break

	assert last_status == 429


def test_update_user_role_cannot_demote_last_admin(monkeypatch):
	db = MagicMock()
	admin_id = uuid4()
	admin_user = SimpleNamespace(id=admin_id, role="admin")

	monkeypatch.setattr(service, "get_user_by_id", lambda db, user_id: admin_user)
	monkeypatch.setattr(service, "_count_admin_users", lambda db: 1)

	with pytest.raises(HTTPException) as exc_info:
		service.update_user_role(db, admin_id, service.UserRole.USER)

	assert exc_info.value.status_code == 400
	assert exc_info.value.detail == "Cannot demote the last admin"


def test_update_user_role_success_for_admin(app_client: TestClient, monkeypatch):
	admin_id = str(uuid4())
	target_id = str(uuid4())

	def _get_user_by_firebase_uid(db, uid):
		return SimpleNamespace(id=admin_id, role="admin")

	def _update_user_role(db, user_id, role):
		return {
			"id": str(user_id),
			"email": "target@example.com",
			"name": "Target User",
			"role": role.value,
			"subscription_plan": "free",
			"created_at": datetime.now(timezone.utc).isoformat(),
		}

	monkeypatch.setattr(service, "get_user_by_firebase_uid", _get_user_by_firebase_uid)
	monkeypatch.setattr(service, "update_user_role", _update_user_role)

	response = app_client.patch(
		f"/auth/users/{target_id}/role",
		json={"role": "admin"},
	)

	assert response.status_code == 200
	assert response.json()["role"] == "admin"


def test_update_user_role_forbidden_for_non_admin(app_client: TestClient, monkeypatch):
	def _get_user_by_firebase_uid(db, uid):
		return SimpleNamespace(id=uuid4(), role="user")

	monkeypatch.setattr(service, "get_user_by_firebase_uid", _get_user_by_firebase_uid)

	response = app_client.patch(
		f"/auth/users/{uuid4()}/role",
		json={"role": "admin"},
	)

	assert response.status_code == 403
	assert response.json()["detail"] == "Admin role required"


def test_update_user_role_not_found(app_client: TestClient, monkeypatch):
	def _get_user_by_firebase_uid(db, uid):
		return SimpleNamespace(id=uuid4(), role="admin")

	def _raise_not_found(db, user_id, role):
		raise HTTPException(status_code=404, detail="User not found")

	monkeypatch.setattr(service, "get_user_by_firebase_uid", _get_user_by_firebase_uid)
	monkeypatch.setattr(service, "update_user_role", _raise_not_found)

	response = app_client.patch(
		f"/auth/users/{uuid4()}/role",
		json={"role": "user"},
	)

	assert response.status_code == 404
	assert response.json()["detail"] == "User not found"
