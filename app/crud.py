from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Station

def get_station_count(db: Session) -> int:
    return db.query(func.count(Station.id)).scalar()

def get_last_updated(db: Session) -> datetime | None:
    result = db.query(func.max(Station.updated_at)).scalar()
    return result

def get_all_stations_as_dicts(db: Session) -> list[dict]:
    """Return all stations as plain dicts compatible with haversine/find_nearest."""
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
    """Delete all existing stations, insert fresh data. Returns count inserted."""
    db.query(Station).delete()
    now = datetime.now(timezone.utc)
    objects = []
    for st in station_dicts:
        try:
            lat = float(st["lat"])
            lon = float(st["lon"])
        except (ValueError, TypeError):
            continue   # skip invalid coordinates silently
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
    db.bulk_save_objects(objects)
    db.commit()
    return len(objects)
