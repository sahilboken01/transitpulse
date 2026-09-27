from contextlib import contextmanager

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database_config import get_database_config


app = FastAPI(title="TransitPulse API")

# The dashboard is served separately from localhost:5500 during development.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@contextmanager
def database_cursor():
    """Open one database connection and always close its cursor and connection."""
    connection = None
    try:
        connection = psycopg2.connect(**get_database_config())
        with connection.cursor() as cursor:
            yield cursor
    except (psycopg2.Error, RuntimeError) as error:
        raise HTTPException(
            status_code=503,
            detail="TransitPulse database is temporarily unavailable",
        ) from error
    finally:
        if connection is not None:
            try:
                connection.close()
            except psycopg2.Error:
                pass


def query_rows(sql, params=None):
    """Run a read query and return its rows after closing database resources."""
    with database_cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def as_float(value):
    return float(value) if value is not None else None


@app.get("/")
def home():
    return {"project": "TransitPulse", "status": "API is running"}


@app.get("/buses")
def get_buses():
    rows = query_rows("""
        SELECT DISTINCT ON (bus_id)
            bus_id, route, speed, latitude, longitude, status, timestamp
        FROM bus_events
        ORDER BY bus_id, timestamp DESC NULLS LAST, id DESC
    """)
    return [
        {
            "bus_id": row[0],
            "route": row[1],
            "speed": as_float(row[2]),
            "latitude": as_float(row[3]),
            "longitude": as_float(row[4]),
            "status": row[5],
            "timestamp": row[6],
        }
        for row in rows
    ]


@app.get("/arrivals")
def get_arrivals():
    rows = query_rows("""
        SELECT bus_id, route, stop, expected_arrival, actual_arrival, delay_seconds
        FROM stop_arrivals
        ORDER BY actual_arrival DESC NULLS LAST, id DESC
        LIMIT 100
    """)
    return [
        {
            "bus_id": row[0],
            "route": row[1],
            "stop": row[2],
            "expected_arrival": row[3],
            "actual_arrival": row[4],
            "delay_seconds": row[5],
        }
        for row in rows
    ]


@app.get("/analytics/routes")
def route_analytics():
    rows = query_rows("""
        SELECT route, ROUND(AVG(speed)::numeric, 2) AS average_speed,
               COUNT(*) AS total_events
        FROM bus_events
        GROUP BY route
        ORDER BY route
    """)
    return [
        {"route": row[0], "average_speed": as_float(row[1]), "total_events": row[2]}
        for row in rows
    ]


@app.get("/analytics/congestion")
def congestion_analytics():
    rows = query_rows("""
        SELECT
            route,
            ROUND(AVG(speed)::numeric, 2) AS average_speed,
            CASE
                WHEN AVG(speed) IS NULL THEN 'Unknown'
                WHEN AVG(speed) >= 30 THEN 'Normal'
                WHEN AVG(speed) >= 20 THEN 'Moderate'
                ELSE 'Congested'
            END AS congestion_level,
            COUNT(*) AS event_count
        FROM bus_events
        GROUP BY route
        ORDER BY route
    """)
    return [
        {
            "route": row[0],
            "average_speed": as_float(row[1]),
            "congestion_level": row[2],
            "event_count": row[3],
        }
        for row in rows
    ]


@app.get("/analytics/delays")
def delay_analytics():
    rows = query_rows("""
        SELECT
            route,
            COUNT(*) AS arrival_count,
            ROUND(AVG(delay_seconds)::numeric, 2) AS average_delay_seconds,
            MAX(delay_seconds) AS maximum_delay_seconds,
            COUNT(*) FILTER (WHERE delay_seconds < 0) AS early_count,
            COUNT(*) FILTER (WHERE delay_seconds = 0) AS on_time_count,
            COUNT(*) FILTER (WHERE delay_seconds > 0) AS late_count
        FROM stop_arrivals
        GROUP BY route
        ORDER BY route
    """)
    return [
        {
            "route": row[0],
            "arrival_count": row[1],
            "average_delay_seconds": as_float(row[2]),
            "maximum_delay_seconds": row[3],
            "early_count": row[4],
            "on_time_count": row[5],
            "late_count": row[6],
        }
        for row in rows
    ]


@app.get("/analytics/summary")
def bus_summary():
    rows = query_rows("""
        WITH latest_buses AS (
            SELECT DISTINCT ON (bus_id) bus_id, status, speed
            FROM bus_events
            ORDER BY bus_id, timestamp DESC NULLS LAST, id DESC
        )
        SELECT
            COUNT(*) AS total_buses,
            COUNT(*) FILTER (WHERE status = 'Normal') AS normal_buses,
            COUNT(*) FILTER (WHERE status = 'Slow') AS slow_buses,
            COUNT(*) FILTER (WHERE status = 'Critical') AS critical_buses,
            COUNT(*) FILTER (WHERE speed < 20) AS congested_buses,
            (SELECT COUNT(*) FROM bus_events) AS total_events
        FROM latest_buses
    """)
    row = rows[0]
    return {
        "total_buses": row[0],
        "normal_buses": row[1],
        "slow_buses": row[2],
        "critical_buses": row[3],
        "congested_buses": row[4],
        "total_events": row[5],
    }


@app.get("/alerts")
def get_alerts():
    rows = query_rows("""
        WITH latest_buses AS (
            SELECT DISTINCT ON (bus_id)
                bus_id, route, speed, status, timestamp
            FROM bus_events
            ORDER BY bus_id, timestamp DESC NULLS LAST, id DESC
        ), route_speeds AS (
            SELECT route, AVG(speed) AS average_speed, MAX(timestamp) AS timestamp
            FROM latest_buses
            GROUP BY route
        )
        SELECT alert_type, severity, bus_id, route, message, timestamp
        FROM (
            SELECT
                'critical_bus'::text AS alert_type,
                'critical'::text AS severity,
                bus_id, route,
                'Bus ' || bus_id || ' has Critical status'
                    || CASE WHEN speed IS NULL THEN ''
                            ELSE ' at ' || ROUND(speed::numeric, 1)::text || ' km/h' END
                    AS message,
                timestamp
            FROM latest_buses
            WHERE status = 'Critical' AND (speed IS NULL OR speed >= 5)

            UNION ALL

            SELECT
                'very_low_speed', 'critical', bus_id, route,
                'Bus ' || bus_id || ' is moving below 5 km/h', timestamp
            FROM latest_buses
            WHERE speed < 5

            UNION ALL

            SELECT
                'congested_route', 'warning', NULL::varchar(20), route,
                'Route ' || route || ' average bus speed is below 20 km/h', timestamp
            FROM route_speeds
            WHERE average_speed < 20

            UNION ALL

            SELECT
                'large_stop_delay',
                CASE WHEN delay_seconds >= 600 THEN 'critical' ELSE 'warning' END,
                bus_id, route,
                'Bus ' || bus_id || ' was delayed ' || delay_seconds || ' seconds at ' || stop,
                actual_arrival AS timestamp
            FROM stop_arrivals
            WHERE delay_seconds >= 300
        ) AS alerts
        ORDER BY timestamp DESC NULLS LAST
        LIMIT 100
    """)
    return [
        {
            "alert_type": row[0],
            "severity": row[1],
            "bus_id": row[2],
            "route": row[3],
            "message": row[4],
            "timestamp": row[5],
        }
        for row in rows
    ]
