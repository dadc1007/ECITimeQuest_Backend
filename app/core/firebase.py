from typing import Any

import firebase_admin
from firebase_admin import auth, credentials
from app.config import settings

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)

def verify_firebase_token(token: str) -> dict[str, Any] | None:
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception:
        return None