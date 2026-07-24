import time
import os
from prometheus_client import start_http_server, Counter, Gauge
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
from service import run_ingestion_cycle
from database import DATABASE_URL

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/ingestion")
METRICS_PORT = int(os.environ.get("METRICS_PORT", "8001"))
INGESTION_INTERVAL = int(os.environ.get("INGESTION_INTERVAL_SECONDS", "300"))

# Prometheus metrics
INGESTION_SUCCESS = Counter("ingestion_cycles_success_total", "Total successful ingestion cycles")
INGESTION_FAILURE = Counter("ingestion_cycles_failure_total", "Total failed ingestion cycles")
INGESTION_DURATION = Gauge("ingestion_duration_seconds", "Duration of last ingestion cycle in seconds")
NEWS_INSERTED = Gauge("news_articles_inserted_last_cycle", "News articles inserted in last cycle")
WEATHER_FETCHED = Gauge("weather_cities_fetched_last_cycle", "Weather cities successfully fetched in last cycle")

def main():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    print(f"Starting metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)

    print(f"Starting ingestion loop, interval: {INGESTION_INTERVAL}s")
    while True:
        print("Running ingestion cycle...")
        session = Session()
        try:
            result = run_ingestion_cycle(session)
            if result["success"]:
                INGESTION_SUCCESS.inc()
            else:
                INGESTION_FAILURE.inc()
            INGESTION_DURATION.set(result["duration_seconds"])
            NEWS_INSERTED.set(result["news_inserted"])
            WEATHER_FETCHED.set(result["weather_success_count"])
            print(f"Cycle complete: {result}")
        except Exception as e:
            INGESTION_FAILURE.inc()
            print(f"Ingestion cycle crashed: {e}")
        finally:
            session.close()

        time.sleep(INGESTION_INTERVAL)

if __name__ == "__main__":
    main()