# TransitPulse

Real-time public transportation intelligence platform built around streaming bus telemetry, geospatial event detection, and operational analytics.

TransitPulse simulates a fleet of buses, streams GPS events through Apache Kafka, processes them in Python, persists operational history in PostgreSQL, exposes analytics through FastAPI, and visualizes the fleet through a browser dashboard.

## Why this project?

Transit systems generate continuous location data, but raw GPS events are not useful on their own. TransitPulse turns that stream into operational signals:

- Current fleet status
- Route-level speed and congestion
- Stop arrival and delay detection
- Historical event analytics
- Database-backed operational alerts

## Architecture

```text
                 ┌──────────────────┐
                 │ Python Simulator │
                 │ 100 bus fleet    │
                 └────────┬─────────┘
                          │ GPS events
                          ▼
                 ┌──────────────────┐
                 │ Apache Kafka     │
                 │ bus-events topic │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Python Processor │
                 │ status + arrival │
                 │ + delay logic    │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ PostgreSQL       │
                 │ events + arrivals│
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ FastAPI          │
                 │ analytics APIs   │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Web Dashboard    │
                 │ Leaflet + JS     │
                 └──────────────────┘
```

## Core capabilities

### Streaming pipeline
- Simulated telemetry for 100 buses
- Kafka `bus-events` topic
- Python producer/consumer workflow
- PostgreSQL persistence for historical events

### Transit intelligence
- Speed-based Normal / Slow / Critical classification
- Haversine-distance arrival detection
- Schedule-relative delay calculation
- Route-level congestion analytics
- Operational alerts for critical conditions and large delays

### Dashboard
- Live fleet map using Leaflet/OpenStreetMap
- Bus status table
- Route and status filters
- Automatically refreshed analytics
- Route speed, congestion, and delay summaries

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/` | API health response |
| GET | `/buses` | Latest state for each bus |
| GET | `/arrivals` | Recent stop arrivals |
| GET | `/analytics/routes` | Route speed and event statistics |
| GET | `/analytics/congestion` | Route congestion analysis |
| GET | `/analytics/delays` | Route delay statistics |
| GET | `/analytics/summary` | Fleet-wide operational summary |
| GET | `/alerts` | Current operational alerts |

Interactive API documentation is available through FastAPI's generated Swagger UI.

## Tech stack

**Backend**
- Python
- FastAPI
- Uvicorn
- kafka-python
- psycopg2

**Data & streaming**
- Apache Kafka 4.0
- PostgreSQL 16
- Docker Compose

**Frontend**
- HTML
- CSS
- JavaScript
- Leaflet
- OpenStreetMap

## Local development

### Prerequisites

- Python
- Docker Desktop
- Docker Compose

### 1. Install dependencies

```powershell
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Configure environment

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Configure the required PostgreSQL variables in `.env`.

### 3. Start infrastructure

```powershell
docker compose up -d
docker compose ps
```

Create the Kafka topic if it does not already exist:

```powershell
docker exec transitpulse-kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic bus-events --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

### 4. Run the services

Start each process in a separate terminal:

```powershell
python simulator.py
```

```powershell
python processor.py
```

```powershell
python -m uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Serve the dashboard:

```powershell
python -m http.server 5500 --directory dashboard
```

Open the dashboard at `http://127.0.0.1:5500`.

FastAPI docs: `http://127.0.0.1:8000/docs`

## Database model

### `bus_events`
Stores GPS telemetry, route, speed, coordinates, derived status, and event timestamp.

### `stop_arrivals`
Stores bus/route/stop information, expected and actual arrival times, calculated delay, and timestamps.

Indexes are created for common fleet, route, and recent-arrival queries.

## Engineering notes

- PostgreSQL credentials are kept outside source control.
- Database failures are surfaced by the API with HTTP 503 responses.
- The current Docker Compose setup is intended for local development.
- The simulator uses deterministic route assignment to make local testing reproducible.

## Project status

This repository is a working local-development implementation. Production deployment would require managed Kafka/PostgreSQL infrastructure, secret management, HTTPS, monitoring, and containerized application services.

## License

No license is currently specified.
