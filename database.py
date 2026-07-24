from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@db:5432/ingestion"
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)