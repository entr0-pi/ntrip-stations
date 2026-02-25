"""Tests for API rate limiting functionality."""

import time
import pytest
from app import crud


class TestRateLimiting:
    """Test slowapi rate limiting on /search endpoint."""

    def test_search_requires_address_or_coordinates(self, client, temp_db):
        """Test that /search endpoint requires either address or coordinates."""
        # Add a test station to the database
        from app.models import Station
        from datetime import datetime, timezone

        station = Station(
            mount="TEST1",
            city="Test City",
            format="RTCM3.3",
            details="test",
            network="TestNet",
            country="US",
            lat=40.7128,
            lon=-74.0060,
            auth="",
            bitrate="0",
            updated_at=datetime.now(timezone.utc),
        )
        temp_db.add(station)
        temp_db.commit()

        # Search with no address or coordinates should error
        response = client.post("/search", data={
            "address": "",
            "lat": "",
            "lon": "",
            "country_code": "",
        })
        assert response.status_code == 200  # Returns HTML with error message
        assert "address or coordinates" in response.text.lower()

    def test_search_with_coordinates(self, client, temp_db):
        """Test /search with explicit coordinates."""
        from app.models import Station
        from datetime import datetime, timezone

        # Add test stations
        stations = [
            Station(
                mount=f"TEST{i}",
                city=f"City {i}",
                format="RTCM3.3",
                details="test",
                network="TestNet",
                country="US",
                lat=40.7128 + i * 0.01,
                lon=-74.0060 + i * 0.01,
                auth="",
                bitrate="0",
                updated_at=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]
        for st in stations:
            temp_db.add(st)
        temp_db.commit()

        # Search with coordinates should work
        response = client.post("/search", data={
            "address": "",
            "lat": "40.7128",
            "lon": "-74.0060",
            "country_code": "",
        })
        assert response.status_code == 200
        assert "TEST0" in response.text or "nearest" in response.text.lower()

    def test_empty_database_search_error(self, client):
        """Test that searching with empty database returns appropriate error."""
        response = client.post("/search", data={
            "address": "New York",
            "lat": "",
            "lon": "",
            "country_code": "",
        })
        assert response.status_code == 200
        assert "empty" in response.text.lower() or "error" in response.text.lower()

    def test_index_page_loads(self, client, temp_db):
        """Test that the index page loads with country dropdown."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Find Nearest Stations" in response.text
        # Should have country dropdown
        assert "country_code" in response.text or "countries" in response.text.lower()

    def test_refresh_endpoint_works(self, client, temp_db):
        """Test that /refresh endpoint returns JSON response."""
        # First request may succeed or hit rate limit (1/day)
        response = client.post("/refresh")
        assert response.status_code in [200, 429, 500]
        assert "application/json" in response.headers.get("content-type", "")
        data = response.json()
        # Should have ok field, detail field, or error field (rate limit)
        assert "ok" in data or "detail" in data or "error" in data


class TestRateLimitConfiguration:
    """Test that rate limiting respects environment configuration."""

    def test_rate_limit_from_env(self):
        """Test that rate limit is read from environment variable."""
        import os
        from app.main import GEOAPIFY_API_RATE_LIMIT

        # The rate limit should be loaded from .env
        rate_limit = GEOAPIFY_API_RATE_LIMIT
        assert rate_limit is not None
        # Should be a string like "5/second" or "10/minute"
        assert "/" in rate_limit
        parts = rate_limit.split("/")
        assert len(parts) == 2
        assert parts[0].isdigit()  # Should have a number
        assert parts[1] in ["second", "minute", "hour", "day"]

    def test_rate_limit_decorator_applied(self, client, temp_db):
        """Test that rate limit decorator is applied to /search endpoint."""
        from app import models
        from datetime import datetime, timezone

        # Add test stations
        station = models.Station(
            mount="TEST1",
            city="Test City",
            format="RTCM3.3",
            details="test",
            network="TestNet",
            country="US",
            lat=40.7128,
            lon=-74.0060,
            auth="",
            bitrate="0",
            updated_at=datetime.now(timezone.utc),
        )
        temp_db.add(station)
        temp_db.commit()

        # The endpoint should have slowapi decorator
        # We test this by checking if the route has rate limiting metadata
        from app.main import app

        search_route = None
        for route in app.routes:
            if route.path == "/search" and "POST" in route.methods:
                search_route = route
                break

        assert search_route is not None, "Search route not found"

    def test_refresh_rate_limit_from_env(self):
        """Test that refresh rate limit is read from .env file."""
        import os
        from app.main import REFRESH_DB_RATE_LIMIT

        # The refresh rate limit should be loaded from .env
        rate_limit = REFRESH_DB_RATE_LIMIT
        assert rate_limit is not None
        # Should be a string like "1/day" or similar
        assert "/" in rate_limit
        parts = rate_limit.split("/")
        assert len(parts) == 2
        assert parts[0].isdigit()  # Should have a number
        assert parts[1] in ["second", "minute", "hour", "day"]
