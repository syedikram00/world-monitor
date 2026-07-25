from unittest.mock import MagicMock, patch

from backend.fetcher import fetch_news, fetch_weather
from backend.service import (
    run_ingestion_cycle,
    store_news,
    store_weather,
)


def test_fetch_news_returns_articles():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "news": [
            {
                "title": "Test Headline",
                "description": "Test description",
                "author": "Test Source",
                "url": "https://example.com/article-1",
                "published": "2026-07-24T10:00:00Z",
            }
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("backend.fetcher.requests.get", return_value=mock_response):
        articles = fetch_news()

    assert len(articles) == 1
    assert articles[0]["title"] == "Test Headline"


def test_fetch_weather_returns_data():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "main": {"temp": 22.5, "humidity": 60},
        "weather": [{"main": "Clear"}],
        "wind": {"speed": 3.4},
    }
    mock_response.raise_for_status.return_value = None

    with patch("backend.fetcher.requests.get", return_value=mock_response):
        data = fetch_weather("London")

    assert data["main"]["temp"] == 22.5


def test_store_news_skips_duplicate_url():
    mock_session = MagicMock()

    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_session.execute.return_value = mock_result

    articles = [
        {
            "title": "Duplicate Article",
            "description": "desc",
            "author": "source",
            "url": "https://example.com/existing-article",
            "published": "2026-07-24T10:00:00Z",
        }
    ]

    inserted_count = store_news(mock_session, articles)

    assert inserted_count == 0
    mock_session.commit.assert_called_once()


def test_store_weather_calls_add_and_commit():
    mock_session = MagicMock()

    data = {
        "main": {"temp": 15.0, "humidity": 70},
        "weather": [{"main": "Rain"}],
        "wind": {"speed": 5.0},
    }

    store_weather(mock_session, "Tokyo", data)

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_run_ingestion_cycle_handles_news_failure_gracefully():
    mock_session = MagicMock()

    with (
        patch(
            "backend.service.fetch_news",
            side_effect=Exception("API down"),
        ),
        patch(
            "backend.service.fetch_weather",
            return_value={
                "main": {"temp": 10.0, "humidity": 50},
                "weather": [{"main": "Cloudy"}],
                "wind": {"speed": 2.0},
            },
        ),
    ):
        result = run_ingestion_cycle(mock_session)

    assert result["success"] is False
    assert result["news_inserted"] == 0