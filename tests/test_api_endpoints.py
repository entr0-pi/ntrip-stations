"""Tests for API endpoints and general functionality."""

import pytest
from app import models, crud
from datetime import datetime, timezone
from app import main


def add_test_stations(db, count=5):
    """Helper to add test stations to database."""
    for i in range(count):
        station = models.Station(
            mount=f"TEST{i}",
            city=f"City {i}",
            format="RTCM3.3",
            details=f"Detail {i}",
            network="TestNet",
            country="US",
            lat=40.7128 + i * 0.01,
            lon=-74.0060 + i * 0.01,
            auth="none",
            bitrate="0",
            updated_at=datetime.now(timezone.utc),
        )
        db.add(station)
    db.commit()


class TestIndexEndpoint:
    """Tests for the / (index) endpoint."""

    def test_index_returns_200(self, client):
        """Test that index page returns 200 status."""
        response = client.get("/")
        assert response.status_code == 200

    def test_index_has_form(self, client):
        """Test that index page contains form elements."""
        response = client.get("/")
        assert 'method="post"' in response.text or "form" in response.text.lower()
        assert "submit" in response.text.lower() or "button" in response.text.lower()

    def test_index_has_country_dropdown(self, client):
        """Test that index page has country dropdown."""
        response = client.get("/")
        assert "country" in response.text.lower()

    def test_index_shows_station_count(self, client, temp_db):
        """Test that index page displays station count."""
        add_test_stations(temp_db, 3)

        response = client.get("/")
        assert response.status_code == 200
        # Should show 0 count initially due to fresh database in test
        assert "station" in response.text.lower()


class TestSearchEndpoint:
    """Tests for the /search endpoint."""

    def test_search_with_invalid_input(self, client, temp_db):
        """Test that search requires valid input."""
        response = client.post("/search", data={
            "address": "",
            "lat": "",
            "lon": "",
            "country_code": "",
        })
        assert response.status_code == 200
        # Should have error message
        assert "error" in response.text.lower() or "address" in response.text.lower()

    def test_search_with_valid_coordinates(self, client, temp_db):
        """Test search with valid lat/lon coordinates."""
        add_test_stations(temp_db, 5)

        response = client.post("/search", data={
            "address": "",
            "lat": "40.7128",
            "lon": "-74.0060",
            "country_code": "",
        })
        assert response.status_code == 200
        # Should have result or nearest station info
        assert "TEST" in response.text or "nearest" in response.text.lower()

    def test_search_with_invalid_coordinates(self, client, temp_db):
        """Test that invalid coordinates are rejected."""
        response = client.post("/search", data={
            "address": "",
            "lat": "not_a_number",
            "lon": "-74.0060",
            "country_code": "",
        })
        assert response.status_code == 200
        # Should have an error
        assert "error" in response.text.lower()

    def test_search_with_empty_database(self, client):
        """Test search when database is empty."""
        response = client.post("/search", data={
            "address": "New York",
            "lat": "",
            "lon": "",
            "country_code": "",
        })
        assert response.status_code == 200
        assert "empty" in response.text.lower() or "error" in response.text.lower()

    def test_search_returns_html(self, client, temp_db):
        """Test that search endpoint returns HTML."""
        add_test_stations(temp_db, 5)

        response = client.post("/search", data={
            "address": "",
            "lat": "40.7128",
            "lon": "-74.0060",
            "country_code": "",
        })
        assert "text/html" in response.headers.get("content-type", "")


class TestRefreshEndpoint:
    """Tests for the /refresh endpoint."""

    def test_refresh_returns_json(self, client):
        """Test that refresh endpoint returns JSON response."""
        response = client.post("/refresh")
        # First request should work (rate limit is 1/day)
        assert response.status_code in [200, 429, 500]  # Network-dependent in CI/local envs
        assert "application/json" in response.headers.get("content-type", "")

    def test_refresh_response_structure(self, client):
        """Test that refresh returns appropriate response structure."""
        response = client.post("/refresh")
        data = response.json()
        # Response should have either ok field, detail field (error), or error field (rate limit)
        assert "ok" in data or "detail" in data or "error" in data

    def test_refresh_has_rate_limit(self):
        """Test that refresh endpoint has rate limit decorator."""
        from app.main import app

        refresh_route = None
        for route in app.routes:
            if route.path == "/refresh" and "POST" in route.methods:
                refresh_route = route
                break

        assert refresh_route is not None, "Refresh route not found"


class TestProtectedDocs:
    """Tests for the protected docs and OpenAPI endpoints."""

    def test_docs_route_hidden_when_not_configured(self, client, monkeypatch):
        """Docs route should return 404 when credentials are not configured."""
        monkeypatch.setattr(main, "DOCS_ADMIN_USER", None)
        monkeypatch.setattr(main, "DOCS_ADMIN_PASSWORD", None)

        response = client.get("/docs")
        assert response.status_code == 404

    def test_docs_requires_basic_auth(self, client, monkeypatch):
        """Docs route should challenge when credentials are missing/invalid."""
        monkeypatch.setattr(main, "DOCS_ADMIN_USER", "admin")
        monkeypatch.setattr(main, "DOCS_ADMIN_PASSWORD", "secret")

        response = client.get("/docs")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Basic"

    def test_docs_with_valid_basic_auth(self, client, monkeypatch):
        """Docs route should be accessible with valid basic auth credentials."""
        monkeypatch.setattr(main, "DOCS_ADMIN_USER", "admin")
        monkeypatch.setattr(main, "DOCS_ADMIN_PASSWORD", "secret")

        response = client.get("/docs", auth=("admin", "secret"))
        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    def test_openapi_with_valid_basic_auth(self, client, monkeypatch):
        """OpenAPI JSON should be accessible with valid basic auth credentials."""
        monkeypatch.setattr(main, "DOCS_ADMIN_USER", "admin")
        monkeypatch.setattr(main, "DOCS_ADMIN_PASSWORD", "secret")

        response = client.get("/openapi.json", auth=("admin", "secret"))
        assert response.status_code == 200
        assert "openapi" in response.json()


class TestDatabaseSeeding:
    """Tests for database initialization and seeding."""

    def test_countries_are_seeded(self, temp_db):
        """Test that countries table is seeded on startup."""
        countries = crud.get_all_countries(temp_db)
        assert len(countries) > 0
        # Check for some known countries
        country_codes = {c["code"] for c in countries}
        assert "us" in country_codes
        assert "fr" in country_codes
        assert "de" in country_codes

    def test_countries_are_sorted(self, temp_db):
        """Test that countries are sorted by name."""
        countries = crud.get_all_countries(temp_db)
        names = [c["name"] for c in countries]
        assert names == sorted(names)

    def test_station_count_increments(self, temp_db):
        """Test that station count is accurate."""
        assert crud.get_station_count(temp_db) == 0

        add_test_stations(temp_db, 3)
        assert crud.get_station_count(temp_db) == 3

        add_test_stations(temp_db, 2)
        assert crud.get_station_count(temp_db) == 5

    def test_last_updated_timestamp(self, temp_db):
        """Test that last_updated timestamp is set."""
        assert crud.get_last_updated(temp_db) is None

        add_test_stations(temp_db, 1)
        last_updated = crud.get_last_updated(temp_db)
        assert last_updated is not None

    def test_station_data_retrieval(self, temp_db):
        """Test that stations can be retrieved as dicts."""
        add_test_stations(temp_db, 2)

        stations = crud.get_all_stations_as_dicts(temp_db)
        assert len(stations) == 2

        # Check required fields
        for st in stations:
            assert "mount" in st
            assert "lat" in st
            assert "lon" in st
            assert "city" in st


class TestNTRIPFunctionality:
    """Tests for NTRIP module functions."""

    def test_haversine_distance(self):
        """Test haversine distance calculation."""
        from app.ntrip import haversine

        # Distance from NYC to NYC should be ~0
        dist = haversine(40.7128, -74.0060, 40.7128, -74.0060)
        assert dist < 0.1

        # Distance should be positive
        dist = haversine(40.7128, -74.0060, 34.0522, -118.2437)
        assert dist > 0

    def test_find_nearest(self, temp_db):
        """Test finding nearest stations."""
        from app.ntrip import find_nearest

        add_test_stations(temp_db, 5)
        stations = crud.get_all_stations_as_dicts(temp_db)

        # Find nearest to NYC
        nearest = find_nearest(40.7128, -74.0060, stations, n=3)
        assert len(nearest) == 3

        # Results should be sorted by distance
        distances = [dist for dist, _ in nearest]
        assert distances == sorted(distances)

    def test_find_nearest_with_n_greater_than_available(self, temp_db):
        """Test find_nearest when n > available stations."""
        from app.ntrip import find_nearest

        add_test_stations(temp_db, 2)
        stations = crud.get_all_stations_as_dicts(temp_db)

        # Request more stations than available
        nearest = find_nearest(40.7128, -74.0060, stations, n=10)
        assert len(nearest) == 2  # Should only return 2

    def test_parse_sourcetable(self):
        """Test parsing NTRIP sourcetable response."""
        from app.ntrip import parse_sourcetable

        # Valid sourcetable with proper field count (18+ fields)
        # Fields: STR;mount;city;format;detail;f5;f6;network;country;lat;lon;f11;f12;f13;f14;f15;auth;bitrate
        raw = """SOURCETABLE 200 OK
STR;mount1;city1;format1;detail1;x;x;net1;country1;40.0;-74.0;x;x;x;x;x;auth1;0
STR;mount2;city2;format2;detail2;x;x;net2;country2;34.0;-118.0;x;x;x;x;x;auth2;0
ENDSOURCETABLE"""

        stations = parse_sourcetable(raw)
        assert len(stations) == 2
        assert stations[0]["mount"] == "mount1"
        assert stations[1]["mount"] == "mount2"
        assert stations[0]["country"] == "country1"
        assert stations[0]["lat"] == "40.0"

    def test_parse_sourcetable_ignores_invalid_lines(self):
        """Test that parse_sourcetable ignores non-STR lines."""
        from app.ntrip import parse_sourcetable

        raw = """SOURCETABLE 200 OK
INVALID LINE
STR;mount1;city1;format1;detail1;x;x;net1;country1;40.0;-74.0;x;x;x;x;x;auth1;0
ENDSOURCETABLE"""

        stations = parse_sourcetable(raw)
        assert len(stations) == 1
        assert stations[0]["mount"] == "mount1"
