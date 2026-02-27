"""Database access layer (CRUD operations) for the RTK2GO Station Finder.

Contains no business logic — just raw database queries and mutations.
All functions take a SQLAlchemy Session dependency injected by FastAPI.
"""

from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Station, Country, SearchLog


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


def log_search(
    db: Session,
    ip: str,
    input_type: str,
    raw_input: str,
    resolved_lat: float | None,
    resolved_lon: float | None,
    resolved_address: str | None,
    success: bool,
) -> None:
    """Insert one search log record and commit immediately.

    Designed to be called after search logic completes. All geocoding-related
    fields are nullable to handle error paths where resolution failed.

    Args:
        db: SQLAlchemy database session.
        ip: Client IP address string from get_client_ip().
        input_type: "address" or "coordinates".
        raw_input: The address string or "lat,lon" string as entered by the user.
        resolved_lat: Final latitude used, or None if search failed before resolution.
        resolved_lon: Final longitude used, or None if search failed before resolution.
        resolved_address: Geocoded display address, or None for coord searches or errors.
        success: True if the search returned station results, False on any error.
    """
    entry = SearchLog(
        ip_address=ip,
        input_type=input_type,
        raw_input=raw_input,
        resolved_lat=resolved_lat,
        resolved_lon=resolved_lon,
        resolved_address=resolved_address,
        success=success,
    )
    db.add(entry)
    db.commit()


def get_search_stats(db: Session) -> dict:
    """Return aggregate search statistics for the admin dashboard.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Dict with keys: total_searches, successful_searches, error_searches,
        unique_ips, searches_today, searches_this_week.
    """
    from datetime import timedelta
    total      = db.query(func.count(SearchLog.id)).scalar() or 0
    successful = db.query(func.count(SearchLog.id)).filter(SearchLog.success == True).scalar() or 0
    errors     = total - successful
    unique_ips = db.query(func.count(func.distinct(SearchLog.ip_address))).scalar() or 0

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start  = today_start - timedelta(days=6)

    searches_today = (
        db.query(func.count(SearchLog.id))
        .filter(SearchLog.timestamp >= today_start)
        .scalar() or 0
    )
    searches_this_week = (
        db.query(func.count(SearchLog.id))
        .filter(SearchLog.timestamp >= week_start)
        .scalar() or 0
    )

    return {
        "total_searches":      total,
        "successful_searches": successful,
        "error_searches":      errors,
        "unique_ips":          unique_ips,
        "searches_today":      searches_today,
        "searches_this_week":  searches_this_week,
    }


def get_recent_searches(db: Session, limit: int = 50) -> list[dict]:
    """Return the most recent search log entries as plain dicts.

    Args:
        db: SQLAlchemy database session.
        limit: Maximum number of rows to return (default 50).

    Returns:
        List of dicts ordered newest-first, each with all SearchLog fields.
        Timestamps are normalized to UTC if stored as naive datetimes.
    """
    rows = (
        db.query(SearchLog)
        .order_by(SearchLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    result = []
    for r in rows:
        ts = r.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        result.append({
            "id":               r.id,
            "timestamp":        ts,
            "ip_address":       r.ip_address,
            "input_type":       r.input_type,
            "raw_input":        r.raw_input,
            "resolved_lat":     r.resolved_lat,
            "resolved_lon":     r.resolved_lon,
            "resolved_address": r.resolved_address,
            "success":          r.success,
        })
    return result


def get_top_ips(db: Session, limit: int = 10) -> list[dict]:
    """Return the most frequent search IPs sorted descending by count.

    Args:
        db: SQLAlchemy database session.
        limit: Maximum number of IP entries to return (default 10).

    Returns:
        List of dicts with keys 'ip' and 'count'.
    """
    rows = (
        db.query(SearchLog.ip_address, func.count(SearchLog.id).label("count"))
        .group_by(SearchLog.ip_address)
        .order_by(func.count(SearchLog.id).desc())
        .limit(limit)
        .all()
    )
    return [{"ip": r.ip_address, "count": r.count} for r in rows]


def get_searches_per_day(db: Session, days: int = 30) -> list[dict]:
    """Return daily search counts for the last N days, zero-filled.

    Uses SQLite's strftime() to group timestamps by date. Days with no
    searches are included with count=0 for a complete series.

    Args:
        db: SQLAlchemy database session.
        days: Number of past days to include (default 30).

    Returns:
        List of dicts with keys 'date' (YYYY-MM-DD string) and 'count' (int),
        ordered oldest to newest.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days - 1)

    rows = (
        db.query(
            func.strftime("%Y-%m-%d", SearchLog.timestamp).label("date"),
            func.count(SearchLog.id).label("count"),
        )
        .filter(SearchLog.timestamp >= cutoff)
        .group_by(func.strftime("%Y-%m-%d", SearchLog.timestamp))
        .order_by(func.strftime("%Y-%m-%d", SearchLog.timestamp))
        .all()
    )

    counts_by_date = {r.date: r.count for r in rows}
    result = []
    for i in range(days):
        d = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        result.append({"date": d, "count": counts_by_date.get(d, 0)})
    return result
