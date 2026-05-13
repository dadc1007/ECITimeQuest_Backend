from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.database import get_db
from app.modules.learning import router as learning_router
from app.modules.learning import service
from app.modules.learning.models import CoinTransaction, ConceptGap, LearningSession, LearningSyncEvent, TopicProgress, UserBadge, UserProgress
from app.modules.learning.schemas import (
	ConceptGapCreate,
	FinishSessionRequest,
	LearningSyncRequest,
	OfflineSessionSyncRequest,
	StartSessionRequest,
	SubmitAnswerRequest,
)


class QuerySequence(list):
	pass


class FakeQuery:
	def __init__(self, result=None):
		self.result = result

	def filter(self, *args, **kwargs):
		return self

	def first(self):
		if isinstance(self.result, list):
			return self.result[0] if self.result else None
		return self.result

	def all(self):
		if isinstance(self.result, list):
			return self.result
		if self.result is None:
			return []
		return [self.result]


class FakeDB:
	def __init__(self, results=None):
		self.results = results or {}
		self.add = MagicMock()
		self.commit = MagicMock()
		self.refresh = MagicMock()
		self.rollback = MagicMock()

	def query(self, model):
		key = model.__name__
		value = self.results.get(key)
		if isinstance(value, QuerySequence):
			item = value.pop(0) if value else None
			return FakeQuery(item)
		return FakeQuery(value)


@pytest.fixture
def app_client() -> TestClient:
	app = FastAPI()
	app.state.limiter = limiter
	app.include_router(learning_router.router)

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
	app.include_router(learning_router.router)

	def fake_get_db():
		yield MagicMock()

	app.dependency_overrides[get_db] = fake_get_db
	return TestClient(app)


def _user(user_id=None):
	return SimpleNamespace(id=user_id or uuid4(), firebase_uid="firebase-test-uid")


def _progress(user_id=None):
	return SimpleNamespace(
		id=uuid4(),
		user_id=user_id or uuid4(),
		xp_total=0,
		level=1,
		coins=0,
		lives=5,
		lives_refill_at=None,
		streak_day=0,
		longest_streak=0,
		last_activity_date=None,
		updated_at=datetime.now(timezone.utc),
	)


def _session(user_id=None, topic_id=None):
	return SimpleNamespace(
		id=uuid4(),
		user_id=user_id or uuid4(),
		topic_id=topic_id or uuid4(),
		xp_gained=0,
		coins_gained=0,
		lives_lost=0,
		completed=False,
		started_at=datetime.now(timezone.utc),
		finished_at=None,
	)


def _topic_progress(user_id=None, topic_id=None):
	return SimpleNamespace(
		id=uuid4(),
		user_id=user_id or uuid4(),
		topic_id=topic_id or uuid4(),
		completion_percentage=0.0,
		xp_earned=0,
		last_studied_at=None,
	)


def _badge(user_id=None, badge_name="streak_7"):
	return SimpleNamespace(
		id=uuid4(),
		user_id=user_id or uuid4(),
		badge_name=badge_name,
		awarded_at=datetime.now(timezone.utc),
	)


def _gap(user_id=None, topic_id=None):
	return SimpleNamespace(
		id=uuid4(),
		user_id=user_id or uuid4(),
		topic_id=topic_id or uuid4(),
		concept="causes",
		error_type="conceptual",
		weakness_score=0.5,
		avg_response_time_ms=500,
		detected_at=datetime.now(timezone.utc),
	)


def test_get_or_create_progress_creates_missing_record():
	user_id = uuid4()
	progress = _progress(user_id)
	db = FakeDB({"UserProgress": None})

	original_query = db.query
	db.query = MagicMock(return_value=FakeQuery(None))
	try:
		result = service.get_or_create_progress(db, user_id)
	finally:
		db.query = original_query

	assert result.user_id == user_id
	db.add.assert_called_once()
	db.commit.assert_called_once()
	db.refresh.assert_called_once()


def test_get_or_create_progress_recovers_from_integrity_error():
	user_id = uuid4()
	progress = _progress(user_id)
	db = FakeDB({"UserProgress": QuerySequence([None, progress])})
	db.commit.side_effect = [IntegrityError("insert", {}, Exception("duplicate")), None]

	result = service.get_or_create_progress(db, user_id)

	assert result.user_id == user_id
	assert db.rollback.called


def test_start_session_rejects_when_no_lives():
	user_id = uuid4()
	db = FakeDB()
	progress = _progress(user_id)
	progress.lives = 0

	original = service.get_or_create_progress
	service.get_or_create_progress = lambda db, uid: progress  # type: ignore[assignment]
	service._refill_lives_if_needed = lambda progress: None  # type: ignore[assignment]
	try:
		with pytest.raises(HTTPException) as exc_info:
			service.start_session(db, user_id, StartSessionRequest(topic_id=uuid4()))
	finally:
		service.get_or_create_progress = original  # type: ignore[assignment]

	assert exc_info.value.status_code == 400


def test_submit_answer_correct_returns_rewards():
	user_id = uuid4()
	session = _session(user_id, uuid4())
	db = FakeDB({"LearningSession": session})

	result = service.submit_answer(
		db,
		user_id,
		session.id,
		SubmitAnswerRequest(
			session_id=session.id,
			question_id=uuid4(),
			answer="answer",
			response_time_ms=1200,
			is_correct=True,
		),
	)

	assert result.is_correct is True
	assert result.xp_earned == 20
	assert result.coins_earned == 5
	assert result.lives_lost == 0
	assert result.feedback == "Correct answer"
	assert db.add.call_count == 0


def test_submit_answer_wrong_creates_concept_gap():
	user_id = uuid4()
	session = _session(user_id, uuid4())
	db = FakeDB({"LearningSession": session})

	result = service.submit_answer(
		db,
		user_id,
		session.id,
		SubmitAnswerRequest(
			session_id=session.id,
			question_id=uuid4(),
			answer="wrong",
			response_time_ms=9000,
			is_correct=False,
		),
	)

	assert result.is_correct is False
	assert result.xp_earned == 0
	assert result.coins_earned == 0
	assert result.lives_lost == 1
	assert result.feedback == "Review this concept and try again"
	assert any(isinstance(call.args[0], ConceptGap) for call in db.add.call_args_list)


def test_submit_answer_session_not_found():
	db = FakeDB({"LearningSession": None})

	with pytest.raises(HTTPException) as exc_info:
		service.submit_answer(
			db,
			uuid4(),
			uuid4(),
			SubmitAnswerRequest(
				session_id=uuid4(),
				question_id=uuid4(),
				answer="x",
				response_time_ms=1000,
				is_correct=True,
			),
		)

	assert exc_info.value.status_code == 404


def test_finish_session_computes_rewards_in_backend():
	user_id = uuid4()
	topic_id = uuid4()
	session = _session(user_id, topic_id)
	progress = _progress(user_id)
	db = FakeDB({"LearningSession": session})

	original_get_progress = service.get_or_create_progress
	original_refill = service._refill_lives_if_needed
	original_update_topic = service._update_topic_progress
	original_award_badges = service._check_and_award_badges
	original_register_coin = service._register_coin_transaction
	service.get_or_create_progress = lambda db, uid: progress  # type: ignore[assignment]
	service._refill_lives_if_needed = lambda progress: None  # type: ignore[assignment]
	topic_spy = MagicMock()
	badge_spy = MagicMock()
	coin_spy = MagicMock()
	service._update_topic_progress = topic_spy  # type: ignore[assignment]
	service._check_and_award_badges = badge_spy  # type: ignore[assignment]
	service._register_coin_transaction = coin_spy  # type: ignore[assignment]
	try:
		result = service.finish_session(
			db,
			user_id,
			session.id,
			FinishSessionRequest(correct_answers=3, wrong_answers=2, avg_response_time_ms=800, completed=True),
		)
	finally:
		service.get_or_create_progress = original_get_progress  # type: ignore[assignment]
		service._refill_lives_if_needed = original_refill  # type: ignore[assignment]
		service._update_topic_progress = original_update_topic  # type: ignore[assignment]
		service._check_and_award_badges = original_award_badges  # type: ignore[assignment]
		service._register_coin_transaction = original_register_coin  # type: ignore[assignment]

	assert result.xp_gained == 110
	assert result.coins_gained == 25
	assert result.lives_lost == 2
	assert progress.xp_total == 110
	assert progress.coins == 25
	assert progress.lives == 3
	assert progress.level == 2
	topic_spy.assert_called_once_with(db, user_id, topic_id, 110, True)
	badge_spy.assert_called_once_with(db, user_id, progress)
	coin_spy.assert_called_once_with(db, user_id, 25, service.CoinReason.LESSON)


def test_finish_session_requires_answers():
	user_id = uuid4()
	session = _session(user_id, uuid4())
	db = FakeDB({"LearningSession": session})
	progress = _progress(user_id)

	original_get_progress = service.get_or_create_progress
	original_refill = service._refill_lives_if_needed
	service.get_or_create_progress = lambda db, uid: progress  # type: ignore[assignment]
	service._refill_lives_if_needed = lambda progress: None  # type: ignore[assignment]
	try:
		with pytest.raises(HTTPException) as exc_info:
			service.finish_session(
				db,
				user_id,
				session.id,
				FinishSessionRequest(correct_answers=0, wrong_answers=0, avg_response_time_ms=None, completed=False),
			)
	finally:
		service.get_or_create_progress = original_get_progress  # type: ignore[assignment]
		service._refill_lives_if_needed = original_refill  # type: ignore[assignment]

	assert exc_info.value.status_code == 400


def test_sync_offline_sessions_creates_session_and_progress():
	user_id = uuid4()
	progress = _progress(user_id)
	topic = SimpleNamespace(id=uuid4(), is_active=True, is_published=True)
	db = FakeDB({"Topic": topic})

	original_get_progress = service.get_or_create_progress
	original_refill = service._refill_lives_if_needed
	service.get_or_create_progress = lambda db, uid: progress  # type: ignore[assignment]
	service._refill_lives_if_needed = lambda progress: None  # type: ignore[assignment]
	try:
		result = service.sync_offline_sessions(
			db,
			user_id,
			LearningSyncRequest(
				sessions=[
					OfflineSessionSyncRequest(
						client_session_id=uuid4(),
						topic_id=uuid4(),
						correct_answers=4,
						wrong_answers=1,
						avg_response_time_ms=1200,
						completed=True,
					),
				]
			),
		)
	finally:
		service.get_or_create_progress = original_get_progress  # type: ignore[assignment]
		service._refill_lives_if_needed = original_refill  # type: ignore[assignment]

	assert result.processed == 1
	assert result.skipped == 0
	assert result.sessions[0].processed is True
	assert progress.xp_total == 130
	assert progress.coins == 30
	assert progress.level == 2
	assert any(isinstance(call.args[0], LearningSession) for call in db.add.call_args_list)
	assert any(isinstance(call.args[0], LearningSyncEvent) for call in db.add.call_args_list)


def test_sync_offline_sessions_skips_duplicates():
	user_id = uuid4()
	existing_event = SimpleNamespace(id=uuid4())
	topic = SimpleNamespace(id=uuid4(), is_active=True, is_published=True)
	db = FakeDB({"Topic": topic, "LearningSyncEvent": QuerySequence([existing_event])})

	result = service.sync_offline_sessions(
		db,
		user_id,
		LearningSyncRequest(
			sessions=[
				OfflineSessionSyncRequest(
					client_session_id=uuid4(),
					topic_id=uuid4(),
					correct_answers=2,
					wrong_answers=0,
					avg_response_time_ms=800,
					completed=False,
				),
			]
		),
	)

	assert result.processed == 0
	assert result.skipped == 1
	assert result.sessions[0].skipped is True


def test_spend_coins_rejects_invalid_amount():
	db = FakeDB()

	with pytest.raises(HTTPException) as exc_info:
		service.spend_coins(db, uuid4(), 0, service.CoinReason.HINT)

	assert exc_info.value.status_code == 400


def test_spend_coins_deducts_and_registers_transaction():
	user_id = uuid4()
	progress = _progress(user_id)
	progress.coins = 50
	db = FakeDB({"UserProgress": progress})

	original = service.get_or_create_progress
	service.get_or_create_progress = lambda db, uid: progress  # type: ignore[assignment]
	try:
		result = service.spend_coins(db, user_id, 20, service.CoinReason.HINT)
	finally:
		service.get_or_create_progress = original  # type: ignore[assignment]

	assert result.coins == 30
	transaction = db.add.call_args_list[-1].args[0]
	assert isinstance(transaction, CoinTransaction)
	assert transaction.amount == -20
	assert transaction.reason == service.CoinReason.HINT


def test_upsert_concept_gap_updates_zero_response_time():
	user_id = uuid4()
	topic_id = uuid4()
	gap = _gap(user_id, topic_id)
	gap.avg_response_time_ms = None
	db = FakeDB({"ConceptGap": gap})

	result = service.upsert_concept_gap(
		db,
		user_id,
		ConceptGapCreate(
			topic_id=topic_id,
			concept="timeline",
			error_type="conceptual",
			weakness_score=0.8,
			avg_response_time_ms=0,
		),
	)

	assert result.avg_response_time_ms == 0


def test_router_get_progress_success(app_client: TestClient, monkeypatch):
	user = _user()
	progress = _progress(user.id)
	monkeypatch.setattr(learning_router.service, "get_or_create_progress", lambda db, user_id: progress)
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.get("/learning/progress")

	assert response.status_code == 200
	assert response.json()["user_id"] == str(user.id)


def test_router_start_session_success(app_client: TestClient, monkeypatch):
	user = _user()
	session = _session(user.id, uuid4())
	monkeypatch.setattr(learning_router.service, "start_session", lambda db, user_id, data: session)
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.post("/learning/sessions/start", json={"topic_id": str(session.topic_id)})

	assert response.status_code == 200
	assert response.json()["topic_id"] == str(session.topic_id)


def test_router_finish_session_success(app_client: TestClient, monkeypatch):
	user = _user()
	session = _session(user.id, uuid4())
	monkeypatch.setattr(learning_router.service, "finish_session", lambda db, user_id, session_id, data: session)
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.post(
		f"/learning/sessions/{session.id}/finish",
		json={"correct_answers": 2, "wrong_answers": 1, "avg_response_time_ms": 900, "completed": True},
	)

	assert response.status_code == 200
	assert response.json()["id"] == str(session.id)


def test_router_sync_offline_sessions_success(app_client: TestClient, monkeypatch):
	user = _user()
	topic_id = uuid4()
	client_session_id = uuid4()
	session = _session(user.id, topic_id)
	monkeypatch.setattr(
		learning_router.service,
		"sync_offline_sessions",
		lambda db, user_id, data: SimpleNamespace(
			processed=1,
			skipped=0,
			sessions=[SimpleNamespace(client_session_id=client_session_id, processed=True, skipped=False, session=session)],
		),
	)
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.post(
		"/learning/sync",
		json={
			"sessions": [
				{
					"client_session_id": str(client_session_id),
					"topic_id": str(topic_id),
					"correct_answers": 3,
					"wrong_answers": 1,
					"avg_response_time_ms": 1200,
					"completed": True,
				}
			]
		},
	)

	assert response.status_code == 200
	assert response.json()["processed"] == 1


def test_router_submit_answer_success(app_client: TestClient, monkeypatch):
	user = _user()
	session = _session(user.id, uuid4())
	response_payload = {
		"session_id": str(session.id),
		"is_correct": True,
		"xp_earned": 20,
		"coins_earned": 5,
		"feedback": "Correct answer",
		"lives_lost": 0,
	}
	monkeypatch.setattr(learning_router.service, "submit_answer", lambda db, user_id, session_id, data: SimpleNamespace(**response_payload))
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.post(
		f"/learning/sessions/{session.id}/answers",
		json={"session_id": str(session.id), "question_id": str(uuid4()), "answer": "ans", "response_time_ms": 1000, "is_correct": True},
	)

	assert response.status_code == 200
	assert response.json()["xp_earned"] == 20


def test_router_submit_answer_not_found(app_client: TestClient, monkeypatch):
	user = _user()
	monkeypatch.setattr(learning_router.service, "submit_answer", lambda db, user_id, session_id, data: (_ for _ in ()).throw(HTTPException(status_code=404, detail="Session not found")))
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.post(
		f"/learning/sessions/{uuid4()}/answers",
		json={"session_id": str(uuid4()), "question_id": str(uuid4()), "answer": "ans", "response_time_ms": 1000, "is_correct": True},
	)

	assert response.status_code == 404


def test_router_get_topic_progress_not_found(app_client: TestClient, monkeypatch):
	user = _user()
	db = MagicMock()
	db.query.return_value.filter.return_value.first.return_value = None

	def fake_get_db():
		yield db

	app_client.app.dependency_overrides[get_db] = fake_get_db
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.get(f"/learning/topics/{uuid4()}/progress")

	assert response.status_code == 404
	assert response.json()["detail"] == "No progress found for this topic"


def test_router_spend_coins_invalid_reason(app_client: TestClient, monkeypatch):
	user = _user()
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.post("/learning/coins/spend", json={"amount": 10, "reason": "invalid"})

	assert response.status_code == 422
	assert response.json()["detail"][0]["loc"][-1] == "reason"


def test_router_get_gaps_and_badges_routes(app_client: TestClient, monkeypatch):
	user = _user()
	gap = _gap(user.id)
	badge = _badge(user.id)
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	db = MagicMock()
	# Simulate three queries: ConceptGap, Topic (id,name), UserBadge
	db.query.side_effect = [
		MagicMock(filter=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[gap])))),
		MagicMock(filter=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[(gap.topic_id, "Topic X")])))),
		MagicMock(filter=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[badge])))),
	]

	def fake_get_db():
		yield db

	app_client.app.dependency_overrides[get_db] = fake_get_db

	gaps_response = app_client.get("/learning/gaps")
	badges_response = app_client.get("/learning/badges")

	assert gaps_response.status_code == 200
	assert badges_response.status_code == 200
	assert gaps_response.json()[0]["id"] == str(gap.id)
	assert badges_response.json()[0]["id"] == str(badge.id)


def test_router_get_period_progress_success(app_client: TestClient, monkeypatch):
	user = _user()
	period_id = uuid4()
	sample = {
		"period_id": str(period_id),
		"period_name": "Ancient Era",
		"topics_count": 2,
		"topics_completed": 1,
		"xp_total": 150,
		"avg_completion": 50.0,
		"topics": [
			{"topic_id": str(uuid4()), "name": "Topic A", "completion_percentage": 100.0, "xp_earned": 100},
			{"topic_id": str(uuid4()), "name": "Topic B", "completion_percentage": 0.0, "xp_earned": 50},
		],
	}

	monkeypatch.setattr(learning_router.service, "get_progress_by_period", lambda db, user_id, pid, include_topics=True: sample)
	monkeypatch.setattr(learning_router, "get_user_by_firebase_uid", lambda db, uid: user)

	response = app_client.get(f"/learning/periods/{period_id}/progress")

	assert response.status_code == 200
	assert response.json()["period_name"] == "Ancient Era"
	assert response.json()["topics_count"] == 2
