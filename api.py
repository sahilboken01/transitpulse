from fastapi import FastAPI
import os
import psycopg2

app = FastAPI(title="TransitPulse API")


def get_connection():
    database_url = os.getenv("DATABASE_URL")

    # Render / cloud database
    if database_url:
        return psycopg2.connect(database_url)

    # Local PostgreSQL database
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="transitpulse",
        user="transitpulse",
        password="transitpulse"
    )


@app.get("/")
def home():
    return {
        "project": "TransitPulse",
        "status": "API is running"
    }


@app.get("/buses")
def get_buses():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT DISTINCT ON (bus_id)
            bus_id,
            route,
            speed,
            latitude,
            longitude,
            status,
            timestamp
        FROM bus_events
        ORDER BY bus_id, timestamp DESC
    """)

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    buses = []

    for row in rows:
        buses.append({
            "bus_id": row[0],
            "route": row[1],
            "speed": row[2],
            "latitude": row[3],
            "longitude": row[4],
            "status": row[5],
            "timestamp": row[6]
        })

    return buses


@app.get("/arrivals")
def get_arrivals():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            bus_id,
            route,
            stop,
            expected_arrival,
            actual_arrival,
            delay_seconds
        FROM stop_arrivals
        ORDER BY actual_arrival DESC
        LIMIT 100
    """)

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    arrivals = []

    for row in rows:
        arrivals.append({
            "bus_id": row[0],
            "route": row[1],
            "stop": row[2],
            "expected_arrival": row[3],
            "actual_arrival": row[4],
            "delay_seconds": row[5]
        })

    return arrivals


@app.get("/analytics/routes")
def route_analytics():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            route,
            ROUND(AVG(speed)::numeric, 2) AS avg_speed,
            COUNT(*) AS total_events
        FROM bus_events
        GROUP BY route
        ORDER BY route
    """)

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    analytics = []

    for row in rows:
        analytics.append({
            "route": row[0],
            "average_speed": float(row[1]),
            "total_events": row[2]
        })

    return analytics