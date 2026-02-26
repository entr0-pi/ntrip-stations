"""RTK2GO NTRIP Station Finder - FastAPI Application

This module defines the main FastAPI application, including:
- HTML rendering routes for the web UI (index, search form)
- Database refresh endpoint for syncing RTK2GO stations
- OpenAPI documentation with HTTP Basic authentication
- Rate limiting, middleware, and request lifecycle management

The app uses SQLAlchemy for database operations and Jinja2 for templating.
"""

import asyncio
import os
import secrets
import jwt
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import engine, get_db, SessionLocal
from app import models, crud
from app.ntrip import fetch_sourcetable, parse_sourcetable, find_nearest, geocode

# Load environment variables
load_dotenv()

# Get absolute path to app directory for templates
APP_DIR = Path(__file__).parent

# Configuration from .env
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
GEOAPIFY_API_RATE_LIMIT = os.getenv("GEOAPIFY_API_RATE_LIMIT", "10/minute")
REFRESH_DB_RATE_LIMIT = os.getenv("REFRESH_DB_RATE_LIMIT", "1/day")
DISTANCE_BADGE_GREEN_KM = int(os.getenv("DISTANCE_BADGE_GREEN_KM", "100"))
DISTANCE_BADGE_YELLOW_KM = int(os.getenv("DISTANCE_BADGE_YELLOW_KM", "300"))

# JWT / login authentication
API_KEY = os.getenv("API_KEY", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_MINUTES = 15

# /refresh endpoint authentication (both optional; endpoint is open if unset)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
DOCS_ADMIN_USER = os.getenv("DOCS_ADMIN_USER")
DOCS_ADMIN_PASSWORD = os.getenv("DOCS_ADMIN_PASSWORD")
REFRESH_ALLOWED_IPS = (
    [ip.strip() for ip in os.getenv("REFRESH_ALLOWED_IPS", "").split(",") if ip.strip()]
    if os.getenv("REFRESH_ALLOWED_IPS")
    else []
)

# Reverse proxy setup: trust X-Forwarded-For from these hosts
# In production, set TRUSTED_HOSTS to your reverse proxy IP (e.g., "127.0.0.1" or internal proxy IPs)
TRUSTED_HOSTS = os.getenv("TRUSTED_HOSTS", "").split(",") if os.getenv("TRUSTED_HOSTS") else ["127.0.0.1"]

# Rate limiter with X-Forwarded-For support
def get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from trusted proxies."""
    # If behind proxy, X-Forwarded-For header is set by reverse proxy
    if request.headers.get("x-forwarded-for"):
        # X-Forwarded-For format: client_ip, proxy1_ip, proxy2_ip
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return request.client.host

limiter = Limiter(key_func=get_client_ip)
security = HTTPBasic(auto_error=False)


# ── JWT helpers ─────────────────────────────────────────────────────────────

def _create_jwt() -> str:
    """Issue a short-lived JWT (15 min)."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=_JWT_EXPIRE_MINUTES)
    return jwt.encode({"exp": exp}, JWT_SECRET_KEY, algorithm=_JWT_ALGORITHM)


def _validate_jwt(request: Request) -> bool:
    """Return True if the request carries a valid JWT cookie."""
    token = request.cookies.get("jwt", "")
    try:
        jwt.decode(token, JWT_SECRET_KEY, algorithms=[_JWT_ALGORITHM])
        return True
    except Exception:
        return False


async def require_jwt(request: Request):
    """FastAPI dependency: raises HTTP 401 if JWT cookie is missing or invalid."""
    if not _validate_jwt(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


def authenticate_docs(credentials: HTTPBasicCredentials | None = Depends(security)):
    """HTTP Basic auth guard for OpenAPI and docs routes."""
    if not DOCS_ADMIN_USER or not DOCS_ADMIN_PASSWORD:
        raise HTTPException(status_code=404, detail="Not Found")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    is_user_ok = secrets.compare_digest(credentials.username, DOCS_ADMIN_USER)
    is_pass_ok = secrets.compare_digest(credentials.password, DOCS_ADMIN_PASSWORD)

    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage FastAPI application lifecycle.

    On startup:
    - Creates database tables if they don't exist (SQLAlchemy models)
    - Seeds the countries table from CSV (one-time initialization)

    This runs once when the app starts and yields until shutdown.
    """
    # Create tables on startup if they don't exist
    models.Base.metadata.create_all(bind=engine)
    # Seed countries table from CSV
    db = SessionLocal()
    try:
        crud.seed_countries(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title="RTK2GO Station Finder",
    version="1.0.0",
    description="Find the nearest RTK2GO NTRIP stations by address or coordinates.",
    contact={
        "name": "NTRIP Stations",
        "url": "https://github.com/entr0-pi/ntrip-stations",
    },
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware for reverse proxy security
# TrustedHostMiddleware protects against Host header attacks
# In production, set ALLOWED_HOSTS env var to your domain(s): "example.com,www.example.com"
allowed_hosts = os.getenv("ALLOWED_HOSTS", "*").split(",") if os.getenv("ALLOWED_HOSTS") != "*" else ["*"]
if allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.globals["BROWSER_SEARCH_COOLDOWN_SECS"] = int(
    os.getenv("BROWSER_SEARCH_COOLDOWN_SECS", "5")
)
templates.env.globals["DISTANCE_BADGE_GREEN_KM"] = DISTANCE_BADGE_GREEN_KM
templates.env.globals["DISTANCE_BADGE_YELLOW_KM"] = DISTANCE_BADGE_YELLOW_KM


@app.get("/docs", include_in_schema=False)
async def docs(_: None = Depends(authenticate_docs)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} Docs")


@app.get("/openapi.json", include_in_schema=False)
async def openapi(_: None = Depends(authenticate_docs)):
    return get_openapi(title=app.title, version="1.0.0", routes=app.routes)


# ── Route 1: Main page ──────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Render the login page. Redirects to / if already authenticated."""
    if _validate_jwt(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", include_in_schema=False)
async def login(request: Request, api_key: str = Form(default="")):
    """Validate API key and issue a JWT cookie. Redirects to / on success."""
    if not API_KEY or not secrets.compare_digest(api_key, API_KEY):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid API key"},
            status_code=401,
        )
    token = _create_jwt()
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        "jwt",
        token,
        httponly=True,
        samesite="lax",
        max_age=_JWT_EXPIRE_MINUTES * 60,
        secure=(ENVIRONMENT == "production"),
    )
    return resp


@app.post("/logout", include_in_schema=False)
async def logout():
    """Clear the JWT cookie and redirect to the login page."""
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("jwt")
    return resp


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
):
    """Render the RTK2GO Station Finder home page.

    Displays the search form with:
    - Total station count in the database
    - Last update timestamp
    - Country selector dropdown
    - Address input and coordinate input fields

    Returns:
        Rendered Jinja2 HTML template with form and metadata.
    """
    if not _validate_jwt(request):
        return RedirectResponse("/login", status_code=302)
    count = crud.get_station_count(db)
    last_updated = crud.get_last_updated(db)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "station_count": count,
        "last_updated": last_updated,
        "countries": crud.get_all_countries(db),
        "selected_country_code": "",
        "result": None,   # no search result yet
        "error": None,
    })


# ── Route 2: Search (POST) ──────────────────────────────────────────────────

@app.post("/search", response_class=HTMLResponse, dependencies=[Depends(require_jwt)])
@limiter.limit(GEOAPIFY_API_RATE_LIMIT)
async def search(request: Request, db: Session = Depends(get_db)):
    """Search for nearest RTK2GO NTRIP stations by address or coordinates.

    Form parameters:
        address: Address string to geocode (e.g., "Paris, France")
        lat: Latitude in decimal degrees (optional if address provided)
        lon: Longitude in decimal degrees (optional if address provided)
        country_code: ISO 3166-1 alpha-2 code to restrict geocoding results

    Rate limiting:
        Applied per IP address via GEOAPIFY_API_RATE_LIMIT (default: 10/minute).
        Uses Geoapify API for address-to-coordinates conversion.

    Returns:
        Rendered HTML template with up to 5 nearest stations and their details,
        or an error message if validation/lookup fails.
    """
    form = await request.form()
    address = form.get("address", "").strip()
    lat_str = form.get("lat", "").strip()
    lon_str = form.get("lon", "").strip()
    country_code = form.get("country_code", "").strip()

    count = crud.get_station_count(db)
    last_updated = crud.get_last_updated(db)

    # Check if database is populated
    if count == 0:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "station_count": count,
            "last_updated": last_updated,
            "countries": crud.get_all_countries(db),
            "selected_country_code": country_code,
            "result": None,
            "error": "Database is empty. Please refresh the station list first.",
        })

    # ── Resolve coordinates from address or direct input ──────────────────
    resolved_address = None
    try:
        if address:
            # Geocode runs in executor to avoid blocking the event loop
            # (Geoapify API calls are blocking I/O, so we run them in a thread pool)
            lat, lon, resolved_address = await asyncio.get_event_loop().run_in_executor(
                None, lambda: geocode(address, country_code or None)
            )
        elif lat_str and lon_str:
            # User provided direct coordinates
            lat, lon = float(lat_str), float(lon_str)
        else:
            raise ValueError("Please enter an address or coordinates.")
    except ValueError as e:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "station_count": count,
            "last_updated": last_updated,
            "countries": crud.get_all_countries(db),
            "selected_country_code": country_code,
            "result": None,
            "error": str(e),
        })

    # ── Find nearest stations using haversine distance ────────────────────
    all_stations = crud.get_all_stations_as_dicts(db)
    nearest = find_nearest(lat, lon, all_stations, n=5)

    if not nearest:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "station_count": count,
            "last_updated": last_updated,
            "countries": crud.get_all_countries(db),
            "selected_country_code": country_code,
            "result": None,
            "error": "No stations found near the specified location.",
        })

    # ── Build result object for template rendering ──────────────────────
    result = {
        "lat": lat,
        "lon": lon,
        "resolved_address": resolved_address,
        "nearest": [
            {
                "rank": i + 1,
                "dist_km": round(dist, 1),
                "mount":   st["mount"],
                "city":    st["city"],
                "country": st["country"],
                "format":  st["format"],
                "details": st["details"],
                "network": st["network"],
                "auth":    st["auth"],
                "bitrate": st["bitrate"],
                "lat":     float(st["lat"]),
                "lon":     float(st["lon"]),
            }
            for i, (dist, st) in enumerate(nearest)
        ],
    }

    return templates.TemplateResponse("index.html", {
        "request": request,
        "station_count": count,
        "last_updated": last_updated,
        "countries": crud.get_all_countries(db),
        "selected_country_code": country_code,
        "result": result,
        "error": None,
    })


# ── Route 3: DB Refresh (async-friendly) ───────────────────────────────────

@app.post("/refresh")
async def refresh_db(request: Request, db: Session = Depends(get_db)):
    """
    Fetch live data from RTK2GO and repopulate SQLite.
    Rate limited by checking last update time in database (not per-IP).
    The blocking socket fetch runs in a thread pool executor so the event loop
    is never blocked. Returns JSON so the frontend can update the UI state.
    """
    # ── Authentication guard ────────────────────────────────────────────────
    if REFRESH_ALLOWED_IPS:
        client_ip = get_client_ip(request)
        if client_ip not in REFRESH_ALLOWED_IPS:
            raise HTTPException(status_code=403, detail="Forbidden: IP not allowed")
    if ADMIN_TOKEN:
        provided_token = request.headers.get("X-Admin-Token", "")
        if not secrets.compare_digest(provided_token, ADMIN_TOKEN):
            raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing X-Admin-Token")
    # ────────────────────────────────────────────────────────────────────────

    try:
        # ── Rate limiting: Check minimum interval since last update ──────────
        last_updated = crud.get_last_updated(db)
        now = datetime.now(timezone.utc)

        if last_updated:
            # Parse REFRESH_DB_RATE_LIMIT format (e.g., "1/day", "3/hour")
            rate_parts = REFRESH_DB_RATE_LIMIT.split("/")
            if len(rate_parts) == 2:
                count_str, unit = rate_parts
                try:
                    count = int(count_str)
                except ValueError:
                    count = 1

                # Convert rate limit unit to timedelta
                if unit == "day":
                    min_interval = timedelta(days=count)
                elif unit == "hour":
                    min_interval = timedelta(hours=count)
                elif unit == "minute":
                    min_interval = timedelta(minutes=count)
                elif unit == "second":
                    min_interval = timedelta(seconds=count)
                else:
                    min_interval = timedelta(days=1)

                # Enforce rate limit: reject if not enough time has passed
                time_since_update = now - last_updated
                if time_since_update < min_interval:
                    hours_remaining = (min_interval - time_since_update).total_seconds() / 3600
                    return JSONResponse(
                        {
                            "error": f"Database was updated {time_since_update.seconds // 3600} hours ago. "
                                     f"Next refresh available in {int(hours_remaining)} hours.",
                        },
                        status_code=429,
                    )

        # ── Fetch and parse RTK2GO sourcetable ──────────────────────────────
        # fetch_sourcetable() makes a raw socket request (blocking I/O)
        # so we run it in a thread executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, fetch_sourcetable)
        station_dicts = parse_sourcetable(raw)
        inserted = crud.replace_all_stations(db, station_dicts)
        last_updated = crud.get_last_updated(db)
        return JSONResponse({
            "ok": True,
            "count": inserted,
            "last_updated": last_updated.isoformat() if last_updated else None,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
