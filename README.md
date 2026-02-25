# RTK2GO Station Finder

A web app to find the 5 nearest RTK2GO NTRIP correction stations from any location. Search by address or coordinates, view results on an interactive map.

🌐 **[See it live!](https://rtk2go.entr0-pi.com)** 🚀

## Features

- 🗺️ Interactive Leaflet map with station markers
- 🔍 Search by address or latitude/longitude with **country filtering**
- 📊 Results table with distance, format, network info
- 📥 **CSV export** button to download the 5 nearest stations
- 💾 SQLite database with refresh button
- 🌙 Light/Dark theme toggle
- 🎨 **Color-coded distance badges** (green/yellow/red) in results table with configurable thresholds
- 🚦 **Dual-layer rate limiting** (browser + server) for Geoapify API protection
- ⚙️ **Environment-based configuration** for all API keys and service settings
- 🔄 **Timestamp-based rate limiting** with informative error messages showing time until next refresh

## Installation

**Prerequisites:** Python 3.11+

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root with your Geoapify API key:

```bash
# Geocoding API (Geoapify)
GEOAPIFY_API_KEY=your_api_key_here

# Rate limiting
GEOAPIFY_API_RATE_LIMIT=5/second
BROWSER_SEARCH_COOLDOWN_SECS=5
REFRESH_DB_RATE_LIMIT=1/day

# Distance badge thresholds (km)
DISTANCE_BADGE_GREEN_KM=100    # Green badge for distances <= this value
DISTANCE_BADGE_YELLOW_KM=300   # Yellow badge for distances <= this value (red beyond)

# RTK2GO NTRIP server
RTK2GO_HOST=rtk2go.com
RTK2GO_PORT=2101
RTK2GO_TIMEOUT_SECS=30
RTK2GO_MAX_BYTES_MB=4

# Earth radius (km) - used for distance calculations
EARTH_RADIUS_KM=6371.0

# Optional docs protection (if unset, /docs and /openapi.json stay hidden)
DOCS_ADMIN_USER=admin
DOCS_ADMIN_PASSWORD=change-me
```

Get a free Geoapify API key at https://www.geoapify.com/

### 3. Run the app

```bash
python run.py
```

Open http://localhost:8000 in your browser.

## Usage

1. Click **"Refresh DB"** to fetch stations from RTK2GO (takes 5-30 seconds)
2. **Search by address** (e.g., "Montreal, Quebec") and optionally select a **country** to narrow results
3. **Or search by coordinates** (latitude/longitude)
4. View the 5 nearest stations on the map with distance in kilometers
5. **Download results as CSV** using the download button below the table
6. Click anywhere on the map to search from that location

### Rate Limiting

The app includes comprehensive rate limiting to protect external APIs and resources:

**Search Endpoint** (Geoapify API):
- **Browser-side:** Search button disables for 5 seconds after each search (instant UX feedback)
- **Server-side:** Hard limit of 5 requests per second per IP address (tamper-proof protection)
- **Rate limit alert:** If the server limit is hit, a warning message appears above the search form and the button is blocked until the limit window resets

**Refresh Endpoint** (RTK2GO NTRIP server):
- **Server-side:** Limited to 1 refresh per day per IP address to prevent excessive downloads

Both search layers and the refresh limit are configurable via `.env` file. Rate limit format supports flexible intervals: `<count>/<unit>` where unit is `second`, `minute`, `hour`, or `day`.

### Distance Badges

Results table displays color-coded badges based on distance:
- 🟢 **Green badge** (≤ 100 km): Nearby stations - closest match
- 🟡 **Yellow badge** (100-300 km): Medium distance
- 🔴 **Red badge** (> 300 km): Far stations

Thresholds are fully customizable via `.env`:
```bash
DISTANCE_BADGE_GREEN_KM=100    # Change to adjust green threshold
DISTANCE_BADGE_YELLOW_KM=300   # Change to adjust yellow threshold
```

## Tech Stack

- **Backend:** FastAPI + Uvicorn + SQLAlchemy
- **Frontend:** Tailwind CSS + DaisyUI + Leaflet.js
- **Database:** SQLite
- **Data:** RTK2GO (NTRIP caster), Geoapify (geocoding)

## Project Structure

```
ntrip-stations/
├── app/
│   ├── main.py          FastAPI routes & rate limiting
│   ├── database.py      SQLAlchemy setup
│   ├── models.py        Station & Country ORM models
│   ├── crud.py          Database operations
│   ├── ntrip.py         NTRIP logic (fetch, parse, geocode, distance)
│   └── templates/
│       └── index.html   Web UI (map, search form, results table)
├── tests/
│   ├── conftest.py      Pytest fixtures & configuration
│   ├── test_rate_limiting.py    Rate limiting tests
│   └── test_api_endpoints.py    API & functionality tests
├── data/
│   └── ISO 3166-1 alpha-2 Country Code List.csv    Country reference data
├── .env                 Environment variables (create this file)
├── .env.example         Example .env template
├── requirements.txt     Python dependencies
├── pytest.ini           Pytest configuration
├── TESTING.md           Testing documentation
├── run.py               Entry point
└── rtk2go.db            SQLite database (auto-created)
```

## Configuration

All service configurations are managed via environment variables in the `.env` file:

### Required Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `GEOAPIFY_API_KEY` | Geocoding API credentials | `abc123...` |

### Optional Variables (with defaults)

| Variable | Purpose | Default |
|----------|---------|---------|
| `GEOAPIFY_API_RATE_LIMIT` | Search API request limit per time unit | `5/second` |
| `REFRESH_DB_RATE_LIMIT` | Database refresh limit per time unit | `1/day` |
| `BROWSER_SEARCH_COOLDOWN_SECS` | Button cooldown after search | `5` |
| `DISTANCE_BADGE_GREEN_KM` | Distance threshold for green badge (nearby) | `100` |
| `DISTANCE_BADGE_YELLOW_KM` | Distance threshold for yellow badge (medium) | `300` |
| `RTK2GO_HOST` | NTRIP server hostname | `rtk2go.com` |
| `RTK2GO_PORT` | NTRIP server port | `2101` |
| `RTK2GO_TIMEOUT_SECS` | Socket connection timeout | `30` |
| `RTK2GO_MAX_BYTES_MB` | Max sourcetable download size | `4` |
| `EARTH_RADIUS_KM` | Earth radius for distance calculations | `6371.0` |
| `DOCS_ADMIN_USER` | Username for protected `/docs` and `/openapi.json` | unset |
| `DOCS_ADMIN_PASSWORD` | Password for protected `/docs` and `/openapi.json` | unset |

Rate limit format supports: `<count>/<unit>` where unit is `second`, `minute`, `hour`, or `day`
- Examples: `5/second`, `10/minute`, `100/hour`

## Testing

The project includes comprehensive test coverage for all major features.

### Run Tests

```bash
# Install test dependencies (already in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_rate_limiting.py -v

# Run with coverage (requires pytest-cov)
pytest tests/ --cov=app --cov-report=html
```

### Test Coverage

- ✅ 30 tests covering:
  - Rate limiting configuration and enforcement (search & refresh endpoints)
  - API endpoints (search, refresh, index)
  - Database operations and seeding
  - NTRIP functions (haversine, nearest stations, sourcetable parsing)
  - Input validation and error handling

See [TESTING.md](TESTING.md) for detailed testing documentation.

## Deployment

For production deployment behind a reverse proxy, see [DEPLOYMENT.md](DEPLOYMENT.md) which includes:

- Step-by-step setup guide for Linux servers
- systemd service configuration
- Reverse proxy configuration requirements
- Rate limiting configuration for proxy environments
- Security best practices and firewall setup
- Monitoring, troubleshooting, and performance tuning

See [examples/.env.production](examples/.env.production) for production environment configuration template.
