from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.schemas import UserCreate


def create_user(db: Session, data: UserCreate) -> User:
    user = User(**data.model_dump())
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        error_message = str(exc.orig).lower() if exc.orig else ""
        if "firebase_uid" in error_message:
            raise HTTPException(status_code=409, detail="Firebase UID already registered")
        raise HTTPException(status_code=409, detail="Email already registered")

def get_user_by_firebase_uid(db: Session, firebase_uid: str) -> User | None:
    return db.query(User).filter(User.firebase_uid == firebase_uid).first()


def upsert_user_from_token(db: Session, token_payload: dict[str, Any]) -> User:
    firebase_uid = token_payload.get("uid")
    email = token_payload.get("email")
    name = token_payload.get("name")

    if not firebase_uid or not email:
        raise HTTPException(status_code=400, detail="Token payload missing uid or email")

    user = get_user_by_firebase_uid(db, firebase_uid)
    if not user:
        return create_user(
            db,
            UserCreate(
                firebase_uid=firebase_uid,
                email=email,
                name=name,
            ),
        )

    changed = False
    if user.email != email:
        user.email = email
        changed = True
    if name is not None and user.name != name:
        user.name = name
        changed = True

    if changed:
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError as exc:
            db.rollback()
            error_message = str(exc.orig).lower() if exc.orig else ""
            if "firebase_uid" in error_message:
                raise HTTPException(status_code=409, detail="Firebase UID already registered")
            raise HTTPException(status_code=409, detail="Email already registered")

    return user



