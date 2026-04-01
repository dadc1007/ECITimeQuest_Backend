from enum import Enum

class SubscriptionPlan(str, Enum):
    FREE = "free"
    SEMI_PREMIUM = "semi_premium"
    PREMIUM = "premium"