from slowapi import Limiter
from slowapi.util import get_remote_address


# Use client IP as the key for basic global protection.
limiter = Limiter(key_func=get_remote_address)
