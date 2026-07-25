from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker  # Changed Sessions to Session
from pathlib import Path
import os
import models
import service 
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/ingestion")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with engine.connect() as conn:
        news = (
            conn.execute(
                text("""
                SELECT id, title, description, source, url, published_at, summary 
                FROM news_events 
                ORDER BY created_at DESC 
                LIMIT 15
            """)
            )
            .mappings()
            .all()
        )

        weather = (
            conn.execute(
                text("""
                SELECT DISTINCT ON (city) city, temperature, humidity, weather_condition, wind_speed, recorded_at
                FROM weather_readings
                ORDER BY city, recorded_at DESC
            """)
            )
            .mappings()
            .all()
        )

    return templates.TemplateResponse(
        "index.html", {"request": request, "news": news, "weather": weather}
    )

@app.post("/articles/{article_id}/summarize")
def generate_article_summary(article_id: int, db: Session = Depends(get_db)):
  try:
    summary = service.summarize_article(db, article_id)
    if not summary:
      raise HTTPException(status_code=404, detail="Article not found")
    return {"summary": summary}
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))