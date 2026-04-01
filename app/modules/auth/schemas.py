from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, EmailStr
from app.enums.enums import SubscriptionPlan


class UserCreate(BaseModel):
    firebase_uid: str
    email: EmailStr
    name: Optional[str] = None
    subscription_plan: SubscriptionPlan = SubscriptionPlan.FREE

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: Optional[str] = None
    subscription_plan: SubscriptionPlan
    created_at: datetime

    model_config = {"from_attributes": True}