"""NTRIP station discovery and geolocation service.
"""

import socket
import math
import json
from urllib.request import urlopen, Request
from urllib.parse import quote

# ── Constants ───────────────────────────────────────────────────────────

HOST = "rtk2go.com"
PORT = 2101
MAX_BYTES = 4 * 1024 * 1024  # 4 MiB
TIMEOUT_S = 30
EARTH_RADIUS_KM = 6371.0
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


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

def geocode(address: str) -> tuple[float, float, str]:
    """Geocode an address to (lat, lon, display_name) via Nominatim.

    Args:
        address: Address or place name string

    Returns:
        Tuple of (latitude, longitude, display_name)

    Raises:
        ValueError: If address not found
    """
    url = f"{NOMINATIM_URL}?q={quote(address)}&format=json&limit=1"
    req = Request(url, headers={"User-Agent": "NTRIP RTK2go PythonClient/1.0"})
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data:
        raise ValueError(f"Address not found: {address}")
    result = data[0]
    return float(result["lat"]), float(result["lon"]), result["display_name"]
