import redis
from app.config import settings


def get_redis_cache() -> redis.Redis:
    """Returns a Redis client configured for the domain cache."""
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
