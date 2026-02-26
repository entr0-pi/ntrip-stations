"""JWT authentication security tests."""

import pytest
import jwt as _jwt
from datetime import datetime, timezone, timedelta

from app import main


class TestLoginPage:
    """Tests for the /login endpoint and login page rendering."""

    def test_login_page_renders(self, client):
        """Test that GET /login renders the login page."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "<form" in response.text

    def test_login_page_redirects_when_authenticated(self, auth_client):
        """Test that GET /login redirects to / if already authenticated."""
        response = auth_client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_login_empty_api_key(self, client, monkeypatch):
        """Test that POST /login with empty API key returns 401."""
        monkeypatch.setattr(main, "API_KEY", "test-api-key")
        response = client.post("/login", data={"api_key": ""})
        assert response.status_code == 401
        assert "Invalid API key" in response.text

    def test_login_wrong_api_key(self, client, monkeypatch):
        """Test that POST /login with wrong API key returns 401."""
        monkeypatch.setattr(main, "API_KEY", "test-api-key")
        response = client.post("/login", data={"api_key": "wrong-key"})
        assert response.status_code == 401
        assert "Invalid API key" in response.text

    def test_login_valid_api_key_redirects(self, client, monkeypatch):
        """Test that POST /login with valid API key redirects to /."""
        monkeypatch.setattr(main, "API_KEY", "test-api-key")
        monkeypatch.setattr(main, "JWT_SECRET_KEY", "test-jwt-secret")
        response = client.post("/login", data={"api_key": "test-api-key"}, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_login_jwt_cookie_is_httponly(self, client, monkeypatch):
        """Test that JWT cookie is set with HttpOnly flag."""
        monkeypatch.setattr(main, "API_KEY", "test-api-key")
        monkeypatch.setattr(main, "JWT_SECRET_KEY", "test-jwt-secret")
        response = client.post("/login", data={"api_key": "test-api-key"}, follow_redirects=False)
        set_cookie = response.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()
        assert "jwt=" in set_cookie


class TestProtectedIndexRoute:
    """Tests for JWT protection on the GET / endpoint."""

    def test_index_redirects_without_jwt(self, client):
        """Test that GET / without JWT redirects to /login."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_index_accessible_with_jwt(self, auth_client):
        """Test that GET / with valid JWT returns 200."""
        response = auth_client.get("/")
        assert response.status_code == 200

    def test_index_rejects_expired_jwt(self, client, monkeypatch):
        """Test that GET / with expired JWT redirects to /login."""
        monkeypatch.setattr(main, "JWT_SECRET_KEY", "test-jwt-secret")
        expired = _jwt.encode(
            {"exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            "test-jwt-secret",
            algorithm="HS256",
        )
        response = client.get("/", cookies={"jwt": expired}, follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_index_rejects_tampered_jwt(self, client, monkeypatch):
        """Test that GET / with JWT signed with wrong secret redirects to /login."""
        monkeypatch.setattr(main, "JWT_SECRET_KEY", "test-jwt-secret")
        tampered = _jwt.encode(
            {"exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret",
            algorithm="HS256",
        )
        response = client.get("/", cookies={"jwt": tampered}, follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]


class TestProtectedSearchRoute:
    """Tests for JWT protection on the POST /search endpoint."""

    def test_search_requires_jwt(self, client):
        """Test that POST /search without JWT returns 401."""
        response = client.post("/search", data={"address": "Paris"})
        assert response.status_code == 401

    def test_search_accessible_with_jwt(self, auth_client):
        """Test that POST /search with valid JWT returns 200."""
        response = auth_client.post("/search", data={
            "address": "",
            "lat": "40.7128",
            "lon": "-74.0060",
            "country_code": "",
        })
        assert response.status_code == 200

    def test_search_rejects_expired_jwt(self, client, monkeypatch):
        """Test that POST /search with expired JWT returns 401."""
        monkeypatch.setattr(main, "JWT_SECRET_KEY", "test-jwt-secret")
        expired = _jwt.encode(
            {"exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            "test-jwt-secret",
            algorithm="HS256",
        )
        response = client.post("/search", data={"address": "Paris"}, cookies={"jwt": expired})
        assert response.status_code == 401

    def test_search_rejects_tampered_jwt(self, client, monkeypatch):
        """Test that POST /search with JWT signed with wrong secret returns 401."""
        monkeypatch.setattr(main, "JWT_SECRET_KEY", "test-jwt-secret")
        tampered = _jwt.encode(
            {"exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret",
            algorithm="HS256",
        )
        response = client.post("/search", data={"address": "Paris"}, cookies={"jwt": tampered})
        assert response.status_code == 401


class TestLogoutRoute:
    """Tests for the POST /logout endpoint."""

    def test_logout_redirects_to_login(self, client):
        """Test that POST /logout redirects to /login."""
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_logout_clears_cookie(self, auth_client):
        """Test that POST /logout clears the JWT cookie."""
        response = auth_client.post("/logout", follow_redirects=False)
        assert response.status_code == 302
        set_cookie = response.headers.get("set-cookie", "")
        assert "jwt" in set_cookie
        # Cookie deletion is indicated by max-age=0 or expires in past
        assert "max-age=0" in set_cookie.lower() or "expires" in set_cookie.lower()

    def test_logout_no_auth_required(self, client):
        """Test that POST /logout does not require authentication."""
        response = client.post("/logout", follow_redirects=False)
        # Should redirect (302) not return 401
        assert response.status_code == 302


class TestRefreshEndpointExempt:
    """Tests that /refresh endpoint does not require JWT."""

    def test_refresh_does_not_require_jwt(self, client, monkeypatch):
        """Test that POST /refresh without JWT does not return 401."""
        monkeypatch.setattr(main, "ADMIN_TOKEN", None)
        monkeypatch.setattr(main, "REFRESH_ALLOWED_IPS", [])
        response = client.post("/refresh")
        # Should NOT be 401 (unauthorized due to JWT)
        # May be 429 (rate limited), 500 (error), or 200 (success)
        assert response.status_code != 401
