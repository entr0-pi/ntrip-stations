"""Database access layer (CRUD operations) for the RTK2GO Station Finder.

Contains no business logic — just raw database queries and mutations.
All functions take a SQLAlchemy Session dependency injected by FastAPI.
"""

from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Station, Country


def get_station_count(db: Session) -> int:
    """Get the total number of stations in the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Total count of Station records (integer).
    """
    return db.query(func.count(Station.id)).scalar()

def get_last_updated(db: Session) -> datetime | None:
    """Get the timestamp of the most recent database refresh.

    Args:
        db: SQLAlchemy database session.

    Returns:
        UTC datetime of the last refresh, or None if no stations are in the DB.
        Note: SQLAlchemy may return a naive (non-timezone-aware) datetime from
        SQLite, so we ensure it has UTC timezone info before returning.
    """
    result = db.query(func.max(Station.updated_at)).scalar()
    # Ensure the datetime is timezone-aware (SQLAlchemy may return naive datetime from SQLite)
    if result and result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result

def get_all_stations_as_dicts(db: Session) -> list[dict]:
    """Return all stations as plain dictionaries for distance calculation.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of station dicts with keys: mount, city, format, details, network,
        country, lat, lon, auth, bitrate.
        Note: lat and lon are returned as strings; the find_nearest function
        converts them to float internally.
    """
    rows = db.query(Station).all()
    return [
        {
            "mount":   r.mount,
            "city":    r.city,
            "format":  r.format,
            "details": r.details,
            "network": r.network,
            "country": r.country,
            "lat":     str(r.lat),   # find_nearest does float() conversion internally
            "lon":     str(r.lon),
            "auth":    r.auth,
            "bitrate": r.bitrate,
        }
        for r in rows
    ]

def replace_all_stations(db: Session, station_dicts: list[dict]) -> int:
    """Delete all existing stations and insert fresh data from RTK2GO sourcetable.

    This is called by the /refresh endpoint. All stations are deleted and
    replaced atomically to avoid stale records. Invalid coordinates are skipped.
    Uses bulk_save_objects for efficiency (much faster than individual inserts).

    Args:
        db: SQLAlchemy database session.
        station_dicts: List of station dicts from parse_sourcetable().

    Returns:
        Number of stations inserted.
    """
    db.query(Station).delete()
    now = datetime.now(timezone.utc)
    objects = []
    for st in station_dicts:
        try:
            lat = float(st["lat"])
            lon = float(st["lon"])
        except (ValueError, TypeError):
            continue   # Skip stations with invalid/missing coordinates
        objects.append(Station(
            mount=st["mount"],
            city=st.get("city", ""),
            format=st.get("format", ""),
            details=st.get("details", ""),
            network=st.get("network", ""),
            country=st.get("country", ""),
            lat=lat,
            lon=lon,
            auth=st.get("auth", ""),
            bitrate=st.get("bitrate", ""),
            updated_at=now,
        ))
    db.bulk_save_objects(objects)  # Much faster than individual inserts
    db.commit()
    return len(objects)

def seed_countries(db: Session) -> int:
    """Populate the countries table from the CSV file on first run.

    Idempotent: Returns 0 if already seeded (skips if any records exist).
    Reads from data/ISO 3166-1 alpha-2 Country Code List.csv and bulk-inserts.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Number of countries inserted (0 if already seeded).
    """
    if db.query(Country).count() > 0:
        return 0  # Already seeded, skip

    csv_path = Path(__file__).parent.parent / "data" / "ISO 3166-1 alpha-2 Country Code List.csv"
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, code = line.split(";", 1)
            rows.append(Country(code=code.strip().lower(), name=name.strip()))

    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)

def get_all_countries(db: Session) -> list[dict]:
    """Return all countries sorted alphabetically by name.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of country dicts with keys: code (ISO 3166-1 alpha-2) and name.
        Sorted by name for UI dropdown rendering.
    """
    rows = db.query(Country).order_by(Country.name).all()
    return [{"code": r.code, "name": r.name} for r in rows]
