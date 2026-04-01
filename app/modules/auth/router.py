from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.security import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.modules.auth import service, schemas

router = APIRouter(prefix="/auth", tags=["Auth"])

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
