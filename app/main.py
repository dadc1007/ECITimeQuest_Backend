from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine

app = FastAPI(title="Mi Backend")

@app.get("/")
def root():
    return {"mensaje": "Hola, el backend está vivo 🚀"}

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada ✅"}