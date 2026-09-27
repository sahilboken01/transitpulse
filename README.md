# TransitPulse

TransitPulse is a real-time public transportation intelligence platform that processes simulated bus telemetry through Kafka, performs stream processing, stores historical data in PostgreSQL, exposes analytics through FastAPI, and visualizes live transit conditions through a web dashboard.

## Architecture

```text
Python simulator
      │ GPS events on bus-events
      ▼
    Kafka
      │
      ▼
Python processor ── bus status and stop arrival/delay detection
      │
      ▼
PostgreSQL ── bus_events and stop_arrivals
      │
      ▼
FastAPI ── current state and analytics endpoints
      │
      ▼
Plain HTML/CSS/JavaScript dashboard ── Leaflet/OpenStreetMap
```

## Technology stack

- Python for the simulator, stream processor, and API
- Apache Kafka 4.0 and PostgreSQL 16 through Docker Compose
- FastAPI and Uvicorn
- psycopg2 for PostgreSQL access
- kafka-python for Kafka producer/consumer access
- A small standard-library helper for loading local `.env` settings
- Plain HTML, CSS, and JavaScript for the dashboard
- Leaflet and OpenStreetMap for map display

## Features

- 100 buses with deterministic route assignment and GPS movement between configured stops
- Kafka `bus-events` telemetry and historical PostgreSQL storage
- Speed-based Normal/Slow/Critical bus status
- Haversine-based arrival detection and schedule-relative delay records
- Route speed and event analytics, rule-based congestion levels, and delay summaries
- Database-backed operational alerts
- Live Leaflet map, fleet table, route/status filters, and automatically refreshed analytics

## Local setup

Use PowerShell from the project directory. Python, Docker Desktop, and Docker Compose must be installed.

Create and activate a virtual environment, then install the project dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a local environment file from the template:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

`.env` is ignored by Git. The values in `.env.example` are for local development only. Use deployment environment variables or a secret manager for deployed environments. The Python API and processor require `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.

## Start Kafka and PostgreSQL

The Compose file reads the PostgreSQL user, password, database, and host port from `.env`.

```powershell
docker compose up -d
docker compose ps
```

Create the Kafka topic once:

```powershell
docker exec transitpulse-kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic bus-events --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

## Run the application

Run one instance of each process in its own terminal, from the project directory with the virtual environment activated. Do not start duplicate simulators or processors.

### Simulator

```powershell
python simulator.py
```

### Processor

```powershell
python processor.py
```

The processor creates `bus_events`, `stop_arrivals`, and the supporting indexes when needed. Indexes use `CREATE INDEX IF NOT EXISTS`; existing records are preserved.

### FastAPI

```powershell
python -m uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

API documentation: `http://127.0.0.1:8000/docs`.

### Dashboard

```powershell
python -m http.server 5500 --directory dashboard
```

Open `http://127.0.0.1:5500`. The dashboard uses the API on port 8000. FastAPI allows local `localhost` and `127.0.0.1` browser origins for this development setup. Leaflet and OpenStreetMap map tiles require internet access.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | API health response |
| GET | `/buses` | Latest event/state for each bus |
| GET | `/arrivals` | Up to 100 recent stop arrivals |
| GET | `/analytics/routes` | Average speed and total GPS event count by route |
| GET | `/analytics/congestion` | Route average speed, congestion level, and event count |
| GET | `/analytics/delays` | Arrival count, average/maximum delay, and early/on-time/late counts by route |
| GET | `/analytics/summary` | Latest bus status totals, congested buses, and total historical events |
| GET | `/alerts` | Current critical/low-speed/congested-route and large-delay alerts |

Database-backed API endpoints return HTTP 503 if PostgreSQL is unavailable; database credentials are not sent to the browser.

## Database

- `bus_events` stores GPS events, route, speed, coordinates, derived status, and event timestamp.
- `stop_arrivals` stores bus/route/stop, expected and actual arrival, delay seconds, and timestamp.
- The processor creates indexes for latest bus lookup, route event lookup, and recent arrival lookup.

## Screenshots

_Add a dashboard screenshot here._

## Deployment

_Deployment placeholder: select a hosting target, provide database/Kafka services, configure environment variables through the host's secret manager, and serve the dashboard over HTTPS._

Do not commit `.env` or put production credentials in source control. The current Compose setup is for local development; the Python processes connect to PostgreSQL through `DB_HOST` and `DB_PORT` and are not containerized by this Compose file.
