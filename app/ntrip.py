"""NTRIP station discovery and geolocation service.

This module provides core functionality for finding RTK2GO NTRIP stations:

1. fetch_sourcetable(): Fetches the live NTRIP sourcetable from rtk2go.com:2101
   via raw TCP socket request (blocking I/O, run in executor).

2. parse_sourcetable(): Parses the raw HTTP response and extracts STR (station)
   records into a list of dictionaries.

3. haversine(): Computes great-circle distance between two lat/lon points
   using the haversine formula. Returns distance in kilometers.

4. find_nearest(): Finds the N nearest stations to a given location using
   haversine distance and returns sorted (distance, station) tuples.

5. geocode(): Converts an address string to (lat, lon, display_name) using
   the Geoapify API. Optionally restricted to a country code.

All configuration (API keys, timeouts, hosts) is loaded from environment
variables in .env.
"""

import socket
import math
import json
import os
import requests
from dotenv import load_dotenv

# ── Load environment variables ──────────────────────────────────────────

load_dotenv()

# ── Constants (configurable via .env) ────────────────────────────────────

# Geoapify geocoding
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")
GEOAPIFY_URL = "https://api.geoapify.com/v1/geocode/search"

# RTK2GO NTRIP server
HOST = os.getenv("RTK2GO_HOST", "rtk2go.com")
PORT = int(os.getenv("RTK2GO_PORT", "2101"))
TIMEOUT_S = int(os.getenv("RTK2GO_TIMEOUT_SECS", "30"))
MAX_BYTES = int(os.getenv("RTK2GO_MAX_BYTES_MB", "4")) * 1024 * 1024

# Earth radius (km) for distance calculations
EARTH_RADIUS_KM = float(os.getenv("EARTH_RADIUS_KM", "6371.0"))


# ── Sourcetable Fetch & Parse (from RTK2GO_Stations.py) ─────────────────

def fetch_sourcetable() -> str:
    """Fetch the RTK2GO NTRIP sourcetable via raw socket.

    Returns the raw HTTP response as a string (ISO-8859-1 encoded).
    Raises socket.timeout or socket.error on failure.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT_S)
    try:
        s.connect((HOST, PORT))
        req = (
            f"GET / HTTP/1.0\r\n"
            f"Host: {HOST}\r\n"
            f"User-Agent: NTRIP StationList/1.0\r\n"
            f"Accept: */*\r\n"
            f"\r\n"
        )
        s.sendall(req.encode("utf-8"))
        data = b""
        while len(data) < MAX_BYTES:
            chunk = s.recv(16384)
            if not chunk:
                break
            data += chunk
        return data.decode("iso-8859-1", errors="replace")
    finally:
        s.close()


def parse_sourcetable(raw: str) -> list[dict]:
    """Parse the NTRIP sourcetable response.

    Extracts STR (station) records and returns a sorted list of dicts.
    Each dict has: mount, city, format, details, network, country, lat, lon, auth, bitrate.

    Args:
        raw: Raw HTTP response from fetch_sourcetable()

    Returns:
        List of station dicts, sorted by (country, mount)
    """
    lines = raw.split("\n")
    status = lines[0].strip() if lines else "?"
    print(f"Statut: {status}\n")

    stations = []
    for line in lines:
        if not line.startswith("STR;"):
            continue
        fields = line.split(";")
        if len(fields) < 18:
            continue
        stations.append({
            "mount":   fields[1],
            "city":    fields[2],
            "format":  fields[3],
            "details": fields[4],
            "network": fields[7],
            "country": fields[8],
            "lat":     fields[9],
            "lon":     fields[10],
            "auth":    fields[16],
            "bitrate": fields[17],
        })

    stations.sort(key=lambda s: (s["country"], s["mount"].lower()))
    return stations


# ── Distance & Nearest (from RTK2GO_Nearest.py) ─────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two lat/lon points.

    Uses the haversine formula.
    """
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def find_nearest(lat: float, lon: float, stations: list, n: int = 5) -> list:
    """Find the n nearest stations from a given position.

    Args:
        lat: Latitude (degrees)
        lon: Longitude (degrees)
        stations: List of station dicts from parse_sourcetable()
        n: Number of nearest to return (default 5)

    Returns:
        List of (distance_km, station_dict) tuples, sorted by distance.
    """
    results = []
    for st in stations:
        try:
            st_lat = float(st["lat"])
            st_lon = float(st["lon"])
        except (ValueError, KeyError, TypeError):
            continue
        if st_lat == 0.0 and st_lon == 0.0:
            continue
        dist = haversine(lat, lon, st_lat, st_lon)
        results.append((dist, st))
    results.sort(key=lambda x: x[0])
    return results[:n]


# ── Geocoding (from RTK2GO_Nearest_Address.py) ──────────────────────────

def geocode(address: str, country_code: str | None = None) -> tuple[float, float, str]:
    """Geocode an address to (lat, lon, display_name) via Geoapify.

    Args:
        address: Address or place name string
        country_code: Optional ISO 3166-1 alpha-2 country code to restrict results

    Returns:
        Tuple of (latitude, longitude, display_name)

    Raises:
        ValueError: If address not found
    """
    params = {"text": address, "apiKey": GEOAPIFY_API_KEY, "limit": 1}
    if country_code:
        params["filter"] = f"countrycode:{country_code.lower()}"
    headers = {"Accept": "application/json"}
    resp = requests.get(GEOAPIFY_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])
    if not features:
        raise ValueError(f"Address not found: {address}")
    props = features[0]["properties"]
    return float(props["lat"]), float(props["lon"]), props["formatted"]
