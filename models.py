from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String)
    source = Column(String)
    url = Column(String, unique=True, nullable=False)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WeatherReading(Base):
    __tablename__ = "weather_readings"

    id = Column(Integer, primary_key=True)
    city = Column(String, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    weather_condition = Column(String)
    wind_speed = Column(Float)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)