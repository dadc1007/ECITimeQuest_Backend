from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from app.database import engine
from app.core.rate_limit import limiter
from app.modules.auth.router import router as auth_router
from app.modules.learning.router import router as learning_router
from app.modules.content.router import router as content_router
import app.modules.auth.models  # noqa: F401
import app.modules.learning.models  # noqa: F401
import app.modules.learning.schemas  # noqa: F401
import app.modules.content.models  # noqa

app = FastAPI(title="Mi Backend")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(content_router)

@app.get("/")
def root():
    return {"mensaje": "Hola, el backend está vivo 🚀"}

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada ✅"}