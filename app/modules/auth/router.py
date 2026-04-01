from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.security import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.modules.auth import service, schemas

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=schemas.UserResponse, responses={
    400: {"description": "User already exists"},
    409: {"description": "Email already registered"},
    429: {"description": "Too many requests"}
})
@limiter.limit("10/minute")
def register_user(request: Request, user_data: schemas.UserCreate, db: Annotated[Session, Depends(get_db)]):
    existing = service.get_user_by_firebase_uid(db, user_data.firebase_uid)
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    return service.create_user(db, user_data)



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
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/login", response_model=schemas.UserResponse, responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found, please register first"},
    429: {"description": "Too many requests"}
})
@limiter.limit("15/minute")
def login(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    user = service.get_user_by_firebase_uid(db, current_user["uid"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found, please register first")
    return user