# Aviation Supply Console

Production-shaped internal ops console for charter supply intelligence using real archive data and OpenSky live states.

## What is implemented

- Real ADS-B Exchange archive importer for monthly `readsb-hist` snapshots
- Aircraft registry importer for `basic-ac-db.json.gz`
- SQL-backed storage for raw ingestion runs, aircraft master data, position events, current aircraft state, and airport supply snapshots
- Simple aircraft classification heuristics to separate likely charter-relevant aircraft from airliners and military traffic
- Airport proximity enrichment using a U.S. airport dataset
- FastAPI JSON API plus a lightweight HTML ops console
- Aircraft detail page with recent position history
- Auto-refreshing ops map for latest charter-relevant aircraft
- OpenSky live collector with anonymous access, optional OAuth2 client credentials, and U.S. bounding-box defaults
- Configurable fallback collector for custom ADS-B-style live feeds

## Data source constraints

- ADS-B Exchange archive samples are real data, but only the `1st` of each month is publicly exposed in the sample bucket.
- ADS-B Exchange states that commercial live use requires an enterprise agreement.
- OpenSky anonymous live access is rate-limited, so the default poll interval is conservative.
- This code is structured so OpenSky can be used immediately and swapped for a licensed live collector later.

## Quick start

```bash
cd /home/kiran/aviation-supply-console
uv venv
source .venv/bin/activate
uv sync
```

Initialize the database:

```bash
aviation-console init-db
```

Import aircraft metadata:

```bash
aviation-console import-registry
```

Import a real archive snapshot:

```bash
aviation-console import-snapshot --when 2026-03-01T00:00:00Z
```

Optionally backfill a window at a custom step:

```bash
aviation-console backfill-window \
  --start 2026-03-01T00:00:00Z \
  --minutes 30 \
  --step-seconds 300
```

Run the app:

```bash
uv run uvicorn aviation_supply_console.app:create_app --factory --reload
```

Open `http://127.0.0.1:8000`.

Open additional pages:

- `http://127.0.0.1:8000/map`
- `http://127.0.0.1:8000/aircraft/<hex_code>`

## Live collector configuration

The app now defaults to the OpenSky live feed with a U.S. bounding box and `5 minute` polling cadence.

Poll one cycle immediately:

```bash
uv run aviation-console poll-live --cycles 1
```

To authenticate with OpenSky API clients, set:

```bash
export AVIATION_OPENSKY_CLIENT_ID="your-client-id"
export AVIATION_OPENSKY_CLIENT_SECRET="your-client-secret"
```

To customize the OpenSky query window:

```bash
export AVIATION_OPENSKY_LAMIN="24.0"
export AVIATION_OPENSKY_LOMIN="-126.0"
export AVIATION_OPENSKY_LAMAX="50.0"
export AVIATION_OPENSKY_LOMAX="-66.0"
```

To use a different provider entirely, switch to the custom collector:

```bash
export AVIATION_LIVE_PROVIDER="custom"
export AVIATION_LIVE_SNAPSHOT_URL="https://your-licensed-feed.example.com/aircraft"
export AVIATION_LIVE_AUTH_HEADER_NAME="api-auth"
export AVIATION_LIVE_AUTH_TOKEN="replace-me"
```

## Useful endpoints

- `GET /api/health`
- `GET /api/ops/summary`
- `GET /api/collector/status`
- `GET /api/aircraft/{hex_code}`
- `GET /api/aircraft/{hex_code}/history`
- `GET /api/airports/{icao}/supply`
- `GET /api/map/aircraft`
- `GET /api/routes/candidates?origin=TEB&destination=OPF`

## Repo layout

- `src/aviation_supply_console/cli.py`: operator commands
- `src/aviation_supply_console/services/ingestion.py`: ADS-B Exchange import pipeline
- `src/aviation_supply_console/services/state_engine.py`: current-state and supply calculations
- `src/aviation_supply_console/api/routes.py`: HTTP API and console pages
