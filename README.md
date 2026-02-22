# RTK2GO Station Finder

A web app to find the 5 nearest RTK2GO NTRIP correction stations from any location. Search by address or coordinates, view results on an interactive map.

## Features

- 🗺️ Interactive Leaflet map with station markers
- 🔍 Search by address or latitude/longitude
- 📊 Results table with distance, format, network info
- 💾 SQLite database with refresh button
- 🌙 Light/Dark theme toggle

## Installation

**Prerequisites:** Python 3.11+

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python run.py
```

Open http://localhost:8000 in your browser.

## Usage

1. Click **"Refresh DB"** to fetch stations from RTK2GO (takes 5-30 seconds)
2. Search by **address** (e.g., "Montreal, Quebec") or **coordinates**
3. View the 5 nearest stations on the map
4. Click anywhere on the map to search from that location

## Tech Stack

- **Backend:** FastAPI + Uvicorn + SQLAlchemy
- **Frontend:** Tailwind CSS + DaisyUI + Leaflet.js
- **Database:** SQLite
- **Data:** RTK2GO (NTRIP caster), Nominatim (geocoding)

## Project Structure

```
ntrip-stations/
├── app/
│   ├── main.py          FastAPI routes
│   ├── database.py      SQLAlchemy setup
│   ├── models.py        Station ORM model
│   ├── crud.py          Database operations
│   ├── ntrip.py         NTRIP logic (fetch, parse, geocode, distance)
│   └── templates/
│       └── index.html   Web UI
├── requirements.txt     Dependencies
├── run.py               Entry point
└── rtk2go.db            SQLite database (auto-created)
```
