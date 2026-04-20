from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.enums.enums import UserRole
from app.core.security import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.modules.auth import service, schemas

router = APIRouter(prefix="/auth", tags=["Auth"])


def _require_admin(current_user: dict, db: Session) -> None:
    role_claim = str(current_user.get("role", "")).lower()
    if role_claim == UserRole.ADMIN.value:
        return

    uid = current_user.get("uid")
    user = service.get_user_by_firebase_uid(db, uid) if uid else None
    if user and user.role == UserRole.ADMIN:
        return

    raise HTTPException(status_code=403, detail="Admin role required")

@router.post("/sync", response_model=schemas.UserResponse, responses={
    400: {"description": "Token payload missing required fields"},
    401: {"description": "Invalid or expired token"},
    409: {"description": "Email or Firebase UID already registered"},
    429: {"description": "Too many requests"}
})
@limiter.limit("15/minute")
def sync_user(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    return service.upsert_user_from_token(db, current_user)

@router.get("/me", response_model=schemas.UserResponse, responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
    429: {"description": "Too many requests"}
})
@limiter.limit("30/minute")
def get_me(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    user = service.get_user_by_firebase_uid(db, current_user["uid"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /auth/sync first.")
    return user


@router.patch("/users/{user_id}/role", response_model=schemas.UserResponse, responses={
    401: {"description": "Invalid or expired token"},
    403: {"description": "Admin role required"},
    404: {"description": "User not found"},
    429: {"description": "Too many requests"},
})
@limiter.limit("10/minute")
def update_user_role(
    request: Request,
    user_id: UUID,
    data: schemas.UserRoleUpdateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.update_user_role(db, user_id, data.role)
