from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums.enums import UserRole
from app.modules.auth.models import User
from app.modules.auth.schemas import UserCreate


def _raise_user_integrity_error(exc: IntegrityError) -> None:
    error_message = str(exc.orig).lower() if exc.orig else ""
    if "firebase_uid" in error_message:
        raise HTTPException(status_code=409, detail="Firebase UID already registered")
    if "email" in error_message:
        raise HTTPException(status_code=409, detail="Email already registered")
    raise HTTPException(status_code=409, detail="User conflict")


def _normalize_role(raw_role: Any) -> UserRole | None:
    if raw_role is None:
        return None
    if isinstance(raw_role, UserRole):
        return raw_role
    if isinstance(raw_role, str):
        normalized = raw_role.strip().lower()
        if normalized == UserRole.ADMIN.value:
            return UserRole.ADMIN
        if normalized == UserRole.USER.value:
            return UserRole.USER
    return None


def _commit_user_changes(db: Session, user: User) -> User:
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        _raise_user_integrity_error(exc)


def _reconcile_user_by_email(
    db: Session,
    firebase_uid: str,
    email: str,
    name: Any,
    role: UserRole | None,
) -> User | None:
    user = get_user_by_email(db, email)
    if not user:
        return None

    user.firebase_uid = firebase_uid
    if name is not None:
        user.name = name
    current_role = getattr(user, "role", UserRole.USER)
    if role is not None and current_role != role:
        user.role = role
    return _commit_user_changes(db, user)


def _sync_existing_user(user: User, email: str, name: Any, role: UserRole | None) -> bool:
    changed = False
    if user.email != email:
        user.email = email
        changed = True
    if name is not None and user.name != name:
        user.name = name
        changed = True
    current_role = getattr(user, "role", UserRole.USER)
    if role is not None and current_role != role:
        user.role = role
        changed = True
    return changed


def _count_admin_users(db: Session) -> int:
    return db.query(User).filter(User.role == UserRole.ADMIN).count()


def create_user(db: Session, data: UserCreate) -> User:
    user = User(**data.model_dump())
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        _raise_user_integrity_error(exc)

def get_user_by_firebase_uid(db: Session, firebase_uid: str) -> User | None:
    return db.query(User).filter(User.firebase_uid == firebase_uid).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def upsert_user_from_token(db: Session, token_payload: dict[str, Any]) -> User:
    firebase_uid = token_payload.get("uid")
    email = token_payload.get("email")
    name = token_payload.get("name")
    role = _normalize_role(token_payload.get("role"))

    if not firebase_uid or not email:
        raise HTTPException(status_code=400, detail="Token payload missing uid or email")

    user = get_user_by_firebase_uid(db, firebase_uid)
    if not user:
        # Reconcile legacy rows created before Firebase-only auth flow.
        reconciled = _reconcile_user_by_email(db, firebase_uid, email, name, role)
        if reconciled:
            return reconciled

        return create_user(
            db,
            UserCreate(
                firebase_uid=firebase_uid,
                email=email,
                name=name,
                role=role or UserRole.USER,
            ),
        )

    if _sync_existing_user(user, email, name, role):
        _commit_user_changes(db, user)

    return user


def update_user_role(db: Session, user_id: UUID, role: UserRole) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == role:
        return user

    if user.role == UserRole.ADMIN and role != UserRole.ADMIN and _count_admin_users(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot demote the last admin")

    user.role = role
    return _commit_user_changes(db, user)



