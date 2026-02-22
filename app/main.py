import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
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
GEOAPIFY_API_RATE_LIMIT = os.getenv("GEOAPIFY_API_RATE_LIMIT", "10/minute")
REFRESH_DB_RATE_LIMIT = os.getenv("REFRESH_DB_RATE_LIMIT", "1/day")
DISTANCE_BADGE_GREEN_KM = int(os.getenv("DISTANCE_BADGE_GREEN_KM", "100"))
DISTANCE_BADGE_YELLOW_KM = int(os.getenv("DISTANCE_BADGE_YELLOW_KM", "300"))

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup if they don't exist
    models.Base.metadata.create_all(bind=engine)
    # Seed countries table from CSV
    db = SessionLocal()
    try:
        crud.seed_countries(db)
    finally:
        db.close()
    yield

app = FastAPI(title="RTK2GO Station Finder", lifespan=lifespan)
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


# ── Route 1: Main page ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
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

@app.post("/search", response_class=HTMLResponse)
@limiter.limit(GEOAPIFY_API_RATE_LIMIT)
async def search(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    address = form.get("address", "").strip()
    lat_str = form.get("lat", "").strip()
    lon_str = form.get("lon", "").strip()
    country_code = form.get("country_code", "").strip()

    count = crud.get_station_count(db)
    last_updated = crud.get_last_updated(db)

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

    # Resolve coordinates
    resolved_address = None
    try:
        if address:
            # Geocode runs in executor to avoid blocking the event loop
            lat, lon, resolved_address = await asyncio.get_event_loop().run_in_executor(
                None, lambda: geocode(address, country_code or None)
            )
        elif lat_str and lon_str:
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

    # Query DB for nearest stations
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

    # Build serialisable result for the template
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
    from datetime import datetime, timezone, timedelta

    try:
        # Check if enough time has passed since last update
        last_updated = crud.get_last_updated(db)
        now = datetime.now(timezone.utc)

        if last_updated:
            # Parse REFRESH_DB_RATE_LIMIT (e.g., "1/day")
            rate_parts = REFRESH_DB_RATE_LIMIT.split("/")
            if len(rate_parts) == 2:
                count_str, unit = rate_parts
                try:
                    count = int(count_str)
                except ValueError:
                    count = 1

                # Calculate minimum time between refreshes
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

                # Check if enough time has passed
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

        # Perform the refresh
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
