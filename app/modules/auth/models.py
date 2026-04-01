from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.enums.enums import SubscriptionPlan
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    subscription_plan = Column(SAEnum(SubscriptionPlan), default=SubscriptionPlan.FREE, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))