<p align="center">
  <img src="docs/assets/logo-mark.svg" alt="Aviation Supply Console logo" width="120">
</p>

<p align="center">
  <img src="docs/assets/banner.svg" alt="Aviation Supply Console banner">
</p>

<p align="center">
  <strong>Internal charter operations intelligence built on real aviation movement data.</strong>
</p>

<p align="center">
  Live OpenSky ingestion • Archive replay • Route candidate ranking • Airport supply snapshots • FastAPI ops console
</p>

## Overview

Aviation Supply Console is a production-shaped internal ops workspace for private aviation marketplaces, charter brokers, and supply intelligence teams.

It ingests real aircraft state data, normalizes and classifies the fleet, computes current aircraft state, and exposes that through:

- an overview dashboard
- an ops map
- aircraft detail pages
- airport supply snapshots
- route candidate APIs for charter matching

## Highlights

- Real OpenSky live ingestion with anonymous access or OAuth2 client credentials
- Real ADS-B Exchange archive backfill for historical replay and state validation
- Stateful aircraft scoring with idle time, last airport, 24h/72h activity, and availability bands
- Charter-relevant filtering for light jets, midsize jets, heavy jets, turboprops, and rotorcraft
- FastAPI app with JSON APIs and lightweight HTML ops surfaces
- Swappable collector model so licensed commercial feeds can replace OpenSky later

## Visuals

### Product identity

<p align="center">
  <img src="docs/assets/logo-mark.svg" alt="Project mark" width="120">
</p>

### System flow

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="System flow diagram">
</p>

## What It Does

| Surface | Purpose |
| --- | --- |
| `Overview` | Shows collector readiness, latest snapshot coverage, top aircraft, and airport supply. |
| `Ops Map` | Displays recent charter-relevant aircraft positions and airport anchors. |
| `Aircraft Detail` | Shows a single aircraft's current state, recent positions, and airport history. |
| `Route Candidate Finder` | Ranks aircraft for routes like `TEB -> OPF` using availability, proximity, and type. |

## Data Sources

| Source | Role | Notes |
| --- | --- | --- |
| `OpenSky /states/all` | Live state vectors | Default live provider. Anonymous access is usable but rate-limited. |
| `ADS-B Exchange readsb-hist` | Historical replay | Public sample data only exposes the `1st` day of each month. |
| `basic-ac-db.json.gz` | Registry enrichment | Adds registrations, ICAO types, manufacturers, and operators. |

## Quick Start

```bash
cd /home/kiran/aviation-supply-console
uv venv
source .venv/bin/activate
uv sync
uv run aviation-console init-db
```

Load registry enrichment:

```bash
uv run aviation-console import-registry
```

Load a real historical archive snapshot:

```bash
uv run aviation-console import-snapshot --when 2026-03-01T00:00:00Z
```

Optional backfill window:

```bash
uv run aviation-console backfill-window \
  --start 2026-03-01T00:00:00Z \
  --minutes 30 \
  --step-seconds 300
```

Run the web app:

```bash
uv run uvicorn aviation_supply_console.app:create_app --factory --reload
```

Open:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/map`
- `http://127.0.0.1:8000/aircraft/<hex_code>`

## Live Collection

The default live path uses OpenSky with a U.S. bounding box and a conservative `5 minute` polling cadence.

Run one live poll:

```bash
uv run aviation-console poll-live --cycles 1
```

Enable authenticated OpenSky polling:

```bash
export AVIATION_OPENSKY_CLIENT_ID="your-client-id"
export AVIATION_OPENSKY_CLIENT_SECRET="your-client-secret"
```

Tune the live query bounds:

```bash
export AVIATION_OPENSKY_LAMIN="24.0"
export AVIATION_OPENSKY_LOMIN="-126.0"
export AVIATION_OPENSKY_LAMAX="50.0"
export AVIATION_OPENSKY_LOMAX="-66.0"
```

Switch to a custom licensed feed:

```bash
export AVIATION_LIVE_PROVIDER="custom"
export AVIATION_LIVE_SNAPSHOT_URL="https://your-licensed-feed.example.com/aircraft"
export AVIATION_LIVE_AUTH_HEADER_NAME="api-auth"
export AVIATION_LIVE_AUTH_TOKEN="replace-me"
```

## API Surface

- `GET /api/health`
- `GET /api/ops/summary`
- `GET /api/collector/status`
- `GET /api/aircraft/{hex_code}`
- `GET /api/aircraft/{hex_code}/history`
- `GET /api/airports/{icao}/supply`
- `GET /api/map/aircraft`
- `GET /api/routes/candidates?origin=TEB&destination=OPF`

## Deployment Notes

This repo is currently optimized for a persistent Python host, not a pure serverless deployment.

- Local default storage uses SQLite and a raw data directory under `data/`
- The live collector is a CLI poller
- A production cloud deployment should move storage to Postgres plus object storage
- For Vercel, the frontend/UI can fit more easily than the current stateful ingestion path

## Repo Layout

- `src/aviation_supply_console/cli.py`: operator commands and live polling
- `src/aviation_supply_console/services/ingestion.py`: archive and live ingestion adapters
- `src/aviation_supply_console/services/state_engine.py`: current aircraft state and airport supply rollups
- `src/aviation_supply_console/api/routes.py`: HTTP routes for HTML pages and JSON APIs
- `src/aviation_supply_console/templates/`: overview, map, and aircraft detail surfaces
- `docs/assets/`: SVG brand and README visuals
