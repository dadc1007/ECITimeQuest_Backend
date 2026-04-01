from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine, Base
from app.modules.auth.router import router as auth_router
import app.modules.auth.models  # noqa: F401 — necesario para que Base conozca la tabla

app = FastAPI(title="Mi Backend")

Base.metadata.create_all(bind=engine)  # crea las tablas si no existen

app.include_router(auth_router)

@app.get("/")
def root():
    return {"mensaje": "Hola, el backend está vivo 🚀"}

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada ✅"}