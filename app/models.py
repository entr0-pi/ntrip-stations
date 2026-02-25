"""SQLAlchemy ORM models for the RTK2GO Station Finder.

This module defines the database schema:
- Country: ISO 3166-1 alpha-2 country code lookup table
- Station: Cached RTK2GO NTRIP station records with geolocation and protocol info

All models inherit from `Base` (DeclarativeBase) defined in database.py.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Country(Base):
    """ISO 3166-1 alpha-2 country code and name lookup table.

    This table is populated once on app startup from the ISO 3166-1 CSV file.
    Used by the geocoding search to restrict results to a specific country.

    Attributes:
        code: ISO 3166-1 alpha-2 country code (e.g., "US", "FR"). Primary key.
        name: Full country name (e.g., "United States", "France").
    """
    __tablename__ = "countries"

    code = Column(String(2), primary_key=True)
    name = Column(String, nullable=False)


class Station(Base):
    """RTK2GO NTRIP station record with geolocation and protocol details.

    Populated by the `/refresh` endpoint, which fetches the sourcetable
    from rtk2go.com:2101. Records are cached locally for fast searches.

    Attributes:
        id: Unique station identifier. Primary key.
        mount: Mount point name (NTRIP identifier). Indexed for quick lookup.
        city: City or location name of the station.
        format: GNSS/RTK message format (e.g., "RTCM3", "CMR").
        details: Additional protocol or format details.
        network: Network name the station belongs to.
        country: Country name (parsed from sourcetable).
        lat: Latitude in decimal degrees (WGS84).
        lon: Longitude in decimal degrees (WGS84).
        auth: Authentication method required (e.g., "D", "N", "Y").
        bitrate: Data bitrate in bits per second.
        updated_at: Timestamp of last refresh (UTC). Auto-set on insert/update.
    """
    __tablename__ = "stations"

    id        = Column(Integer, primary_key=True, index=True)
    mount     = Column(String, nullable=False, index=True)
    city      = Column(String)
    format    = Column(String)
    details   = Column(String)
    network   = Column(String)
    country   = Column(String)
    lat       = Column(Float)
    lon       = Column(Float)
    auth      = Column(String)
    bitrate   = Column(String)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
