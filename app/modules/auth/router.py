from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.modules.auth import service, schemas

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=schemas.UserResponse, responses={400: {"description": "User already exists"}})
def register_user(user_data: schemas.UserCreate, db: Annotated[Session, Depends(get_db)]):
    existing = service.get_user_by_firebase_uid(db, user_data.firebase_uid)
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    return service.create_user(db, user_data)