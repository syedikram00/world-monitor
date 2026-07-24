from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
import datetime
import time

from models import NewsEvent, WeatherReading
from fetcher import fetch_news, fetch_weather, CITIES

def store_news(session: Session, articles):
    inserted_count = 0
    for article in articles:
        stmt = insert(NewsEvent).values(
            title=article.get("title"),
            description=article.get("description"),
            source=article.get("author") or "unknown",
            url=article.get("url"),
            published_at=article.get("published")
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
        recorded_at=datetime.datetime.utcnow()
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
        "weather_success_count": weather_success_count
    }