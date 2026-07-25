from dotenv import load_dotenv
import requests
import os

load_dotenv()

CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

CURRENTS_URL = "https://api.currentsapi.services/v1/latest-news"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

CITIES = ["London", "New York", "Tokyo", "Karachi", "Sydney"]

def fetch_news():
    response = requests.get(CURRENTS_URL, params={"apiKey": CURRENTS_API_KEY, "language": "en"}, timeout=10)
    response.raise_for_status()
    return response.json().get("news", [])

def fetch_weather(city: str):
    response = requests.get(OPENWEATHER_URL, params={
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }, timeout=10)
    response.raise_for_status()
    return response.json()

