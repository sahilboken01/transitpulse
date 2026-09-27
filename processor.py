import json
import math
from datetime import datetime, timedelta
import psycopg2
from kafka import KafkaConsumer
from stop import ROUTE_STOPS
from database_config import get_database_config


ARRIVAL_RADIUS_METERS = 50
EARTH_RADIUS_METERS = 6_371_000
SCHEDULE_CYCLE_SECONDS = 900  # Three five-minute stop intervals.


def haversine_distance_meters(latitude1, longitude1, latitude2, longitude2):
    """Return the great-circle distance between two GPS points in meters."""
    # Haversine uses the coordinates' angular differences on Earth's surface.
    latitude1, longitude1, latitude2, longitude2 = map(
        math.radians, (latitude1, longitude1, latitude2, longitude2)
    )
    latitude_delta = latitude2 - latitude1
    longitude_delta = longitude2 - longitude1

    a = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude1)
        * math.cos(latitude2)
        * math.sin(longitude_delta / 2) ** 2
    )
    # Clamp for floating-point rounding near the ends of the valid range.
    a = min(1.0, max(0.0, a))
    return 2 * EARTH_RADIUS_METERS * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def detect_arrival(event, bus_states):
    """Record one arrival when a bus reaches its next expected route stop."""
    bus_id = event["bus_id"]
    route = event["route"]
    if route not in ROUTE_STOPS:
        raise ValueError(f"Bus {bus_id} has unknown route {route!r}")

    event_time = datetime.fromisoformat(event["timestamp"])

    # Keep each bus's route, expected stop index, and schedule anchor in memory.
    if bus_id not in bus_states:
        bus_states[bus_id] = {
            "route": route,
            # Simulator publishes after leaving stop 0, heading to stop 1.
            "next_stop_index": 1 % len(ROUTE_STOPS[route]),
            # The first GPS event seen becomes this run's relative schedule start.
            "schedule_anchor": event_time,
        }

    state = bus_states[bus_id]
    if state["route"] != route:
        raise ValueError(
            f"Bus {bus_id} route changed from {state['route']!r} to {route!r}"
        )

    stops = ROUTE_STOPS[route]
    stop_index = state["next_stop_index"]
    target_stop = stops[stop_index]
    distance = haversine_distance_meters(
        event["latitude"],
        event["longitude"],
        target_stop["latitude"],
        target_stop["longitude"],
    )

    # Only the current target can trigger an arrival. Advancing the index after
    # recording ensures repeated GPS events near this stop do not record twice.
    if distance > ARRIVAL_RADIUS_METERS:
        return None

    expected_arrival = state["schedule_anchor"] + timedelta(
        seconds=target_stop["scheduled_offset_seconds"]
    )
    actual_arrival = event_time
    # Positive delay means late; negative delay means early.
    delay_seconds = int((actual_arrival - expected_arrival).total_seconds())

    state["next_stop_index"] = (stop_index + 1) % len(stops)
    if state["next_stop_index"] == 0:
        # Start the next route loop after one complete 15-minute schedule cycle.
        state["schedule_anchor"] += timedelta(seconds=SCHEDULE_CYCLE_SECONDS)

    return {
        "bus_id": bus_id,
        "route": route,
        "stop": target_stop["stop"],
        "expected_arrival": expected_arrival,
        "actual_arrival": actual_arrival,
        "delay_seconds": delay_seconds,
        "timestamp": event_time,
    }


# Connect to PostgreSQL
connection = psycopg2.connect(**get_database_config())

cursor = connection.cursor()


# Create table if it doesn't already exist
cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_events (
        id SERIAL PRIMARY KEY,
        bus_id VARCHAR(20),
        route VARCHAR(20),
        speed FLOAT,
        latitude FLOAT,
        longitude FLOAT,
        status VARCHAR(20),
        timestamp TIMESTAMP
    )
""")

# Keep arrival and delay records separate from the existing GPS event table.
cursor.execute("""
    CREATE TABLE IF NOT EXISTS stop_arrivals (
        id SERIAL PRIMARY KEY,
        bus_id VARCHAR(20),
        route VARCHAR(20),
        stop VARCHAR(50),
        expected_arrival TIMESTAMP,
        actual_arrival TIMESTAMP,
        delay_seconds INTEGER,
        timestamp TIMESTAMP
    )
""")

# These indexes support latest-bus, route analytics, and recent-arrival queries.
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_bus_events_bus_timestamp
    ON bus_events (bus_id, timestamp DESC, id DESC)
""")
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_bus_events_route_timestamp
    ON bus_events (route, timestamp DESC)
""")
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_stop_arrivals_route_actual
    ON stop_arrivals (route, actual_arrival DESC)
""")
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_stop_arrivals_bus_actual
    ON stop_arrivals (bus_id, actual_arrival DESC)
""")
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_stop_arrivals_actual
    ON stop_arrivals (actual_arrival DESC)
""")

connection.commit()


# Connect to Kafka
consumer = KafkaConsumer(
    "bus-events",
    bootstrap_servers="localhost:9092",
    auto_offset_reset="latest",
    value_deserializer=lambda value: json.loads(value.decode("utf-8"))
)


print("Processor started. Waiting for bus events...")

# The next-stop index and schedule anchor live for this processor run.
bus_states = {}


for message in consumer:

    event = message.value
    arrival = detect_arrival(event, bus_states)

    # Process the event
    if event["speed"] < 10:
        status = "Critical"
    elif event["speed"] < 20:
        status = "Slow"
    else:
        status = "Normal"

    # Store processed event in PostgreSQL
    cursor.execute("""
        INSERT INTO bus_events
        (bus_id, route, speed, latitude, longitude, status, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        event["bus_id"],
        event["route"],
        event["speed"],
        event["latitude"],
        event["longitude"],
        status,
        event["timestamp"]
    ))

    if arrival is not None:
        cursor.execute("""
            INSERT INTO stop_arrivals
            (bus_id, route, stop, expected_arrival, actual_arrival,
             delay_seconds, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            arrival["bus_id"],
            arrival["route"],
            arrival["stop"],
            arrival["expected_arrival"],
            arrival["actual_arrival"],
            arrival["delay_seconds"],
            arrival["timestamp"],
        ))
        print(
            arrival["bus_id"], "|", arrival["route"], "|", arrival["stop"],
            "| Delay seconds:", arrival["delay_seconds"]
        )

    connection.commit()

    print(
        event["bus_id"],
        "|",
        event["route"],
        "| Speed:", event["speed"],
        "| Status:", status
    )
