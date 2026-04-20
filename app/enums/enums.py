from enum import Enum

class SubscriptionPlan(str, Enum):
    FREE = "free"
    SEMI_PREMIUM = "semi_premium"
    PREMIUM = "premium"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class ErrorType(str, Enum):
    FACTUAL = "factual"
    CONCEPTUAL = "conceptual"
    CONTEXTUAL = "contextual"

class CoinReason(str, Enum):
    LESSON = "lesson"
    STREAK = "streak"
    CHALLENGE = "challenge"
    REVIVE_LIFE = "revive_life"
    HINT = "hint"