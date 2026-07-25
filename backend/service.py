import datetime
import os
import time
from google import genai
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fetcher import CITIES, fetch_news, fetch_weather
import models
from models import NewsEvent, WeatherReading

# Initialize Gemini Client safely
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Primary model candidate list to attempt in order
MODEL_CANDIDATES = [
    "gemini-2.0-flash",
    "gemini-3.5-flash",
    "gemini-1.5-flash-latest",
]


def _generate_with_fallback(prompt: str) -> str:
  """Attempts generation using defined models or dynamically finds an available model."""
  # 1. Attempt primary candidate models
  for model_name in MODEL_CANDIDATES:
    try:
      response = client.models.generate_content(
          model=model_name, contents=prompt
      )
      if response.text:
        return response.text.strip()
    except Exception as e:
      print(f"[DEBUG] Model {model_name} unavailable: {e}")
      continue

  # 2. Dynamic Fallback: Query API for any available supported model
  try:
    for m in client.models.list():
      # Pick the first available flash model supporting generateContent
      if "generateContent" in getattr(m, "supported_generation_methods", []):
        model_id = m.name.replace("models/", "")
        try:
          response = client.models.generate_content(
              model=model_id, contents=prompt
          )
          if response.text:
            return response.text.strip()
        except Exception:
          continue
  except Exception as list_err:
    print(f"[ERROR] Failed to list available models: {list_err}")

  raise RuntimeError(
      "No valid Gemini model available for the provided API key."
  )


def summarize_article(db: Session, article_id: int) -> str:
  if not client:
    raise ValueError(
        "GEMINI_API_KEY is not configured in environment variables"
    )

  # Fetch article from news_events
  article = db.query(NewsEvent).filter(NewsEvent.id == article_id).first()
  if not article:
    return None

  # Return cached summary if it already exists
  if article.summary:
    return article.summary

  # Use description as main content, falling back to title if description is empty
  content_to_summarize = article.description or article.title

  prompt = f"""
    You are a world-news editor. Summarize the following news article in 2-3 concise, high-impact bullet points:
    
    Title: {article.title}
    Content: {content_to_summarize}
    """

  try:
    summary_text = _generate_with_fallback(prompt)

    # Store summary back in database
    article.summary = summary_text
    db.commit()

    return article.summary

  except Exception as e:
    db.rollback()
    print(
        f"[ERROR] Gemini API Summarization failed for article ID {article_id}: {e}"
    )
    raise e


def store_news(session: Session, articles):
  inserted_count = 0
  for article in articles:
    stmt = insert(NewsEvent).values(
        title=article.get("title"),
        description=article.get("description"),
        source=article.get("author") or "unknown",
        url=article.get("url"),
        published_at=article.get("published"),
    ).on_conflict_do_nothing(index_elements=["url"])
    result = session.execute(stmt)
    if result.rowcount:
      inserted_count += 1
  session.commit()
  return inserted_count


def store_weather(session: Session, city: str, data: dict):
  reading = WeatherReading(
      city=city,
      temperature=data["main"]["temp"],
      humidity=data["main"]["humidity"],
      weather_condition=data["weather"][0]["main"],
      wind_speed=data["wind"]["speed"],
      recorded_at=datetime.datetime.utcnow(),
  )
  session.add(reading)
  session.commit()


def run_ingestion_cycle(session: Session):
  start = time.time()
  success = True

  try:
    articles = fetch_news()
    news_inserted = store_news(session, articles)
  except Exception as e:
    print(f"News ingestion failed: {e}")
    success = False
    news_inserted = 0

  weather_success_count = 0
  for city in CITIES:
    try:
      data = fetch_weather(city)
      store_weather(session, city, data)
      weather_success_count += 1
    except Exception as e:
      print(f"Weather ingestion failed for {city}: {e}")
      success = False

  duration = time.time() - start
  return {
      "success": success,
      "duration_seconds": duration,
      "news_inserted": news_inserted,
      "weather_success_count": weather_success_count,
  }