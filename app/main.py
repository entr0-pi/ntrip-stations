import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app import models, crud
from app.ntrip import fetch_sourcetable, parse_sourcetable, find_nearest, geocode

# Get absolute path to app directory for templates
APP_DIR = Path(__file__).parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup if they don't exist
    models.Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="RTK2GO Station Finder", lifespan=lifespan)
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


# ── Route 1: Main page ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    count = crud.get_station_count(db)
    last_updated = crud.get_last_updated(db)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "station_count": count,
        "last_updated": last_updated,
        "result": None,   # no search result yet
        "error": None,
    })


# ── Route 2: Search (POST) ──────────────────────────────────────────────────

@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    address = form.get("address", "").strip()
    lat_str = form.get("lat", "").strip()
    lon_str = form.get("lon", "").strip()

    count = crud.get_station_count(db)
    last_updated = crud.get_last_updated(db)

    if count == 0:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "station_count": count,
            "last_updated": last_updated,
            "result": None,
            "error": "Database is empty. Please refresh the station list first.",
        })

    # Resolve coordinates
    resolved_address = None
    try:
        if address:
            # Geocode runs in executor to avoid blocking the event loop
            lat, lon, resolved_address = await asyncio.get_event_loop().run_in_executor(
                None, geocode, address
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
        "result": result,
        "error": None,
    })


# ── Route 3: DB Refresh (async-friendly) ───────────────────────────────────

@app.post("/refresh")
async def refresh_db(db: Session = Depends(get_db)):
    """
    Fetch live data from RTK2GO and repopulate SQLite.
    The blocking socket fetch runs in a thread pool executor so the event loop
    is never blocked. Returns JSON so the frontend can update the UI state.
    """
    try:
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
