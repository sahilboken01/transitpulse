import random
import time
import json
import math
from datetime import datetime
from kafka import KafkaProducer
from stop import ROUTE_STOPS


UPDATE_INTERVAL_SECONDS = 2
METERS_PER_DEGREE = 111_320


# Connect to Kafka
producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda value: json.dumps(value).encode("utf-8")
)


def create_bus(bus_id, bus_number):
    routes = list(ROUTE_STOPS)
    # Assign by the numeric bus index for a stable, even distribution.
    route = routes[bus_number % len(routes)]
    stops = ROUTE_STOPS[route]
    return {
        "bus_id": bus_id,
        "route": route,
        # Keep the one-time assignment so updates can detect accidental changes.
        "assigned_route": route,
        "speed": random.randint(20, 40),
        # Start at the first stop and head toward the second one.
        "latitude": stops[0]["latitude"],
        "longitude": stops[0]["longitude"],
        "next_stop_index": 1 % len(stops)
    }


def update_bus(bus):
    route = bus.get("route")
    if route not in ROUTE_STOPS:
        raise ValueError(
            f"Bus {bus.get('bus_id', '<unknown>')} has invalid route {route!r}; "
            f"expected one of {', '.join(ROUTE_STOPS)}"
        )

    assigned_route = bus.get("assigned_route")
    if assigned_route is None:
        # Support bus state created before the route binding was added.
        bus["assigned_route"] = route
        assigned_route = route
    if route != assigned_route:
        raise ValueError(
            f"Bus {bus.get('bus_id', '<unknown>')} route changed from "
            f"{assigned_route!r} to {route!r}"
        )

    stops = ROUTE_STOPS[route]
    next_stop = stops[bus["next_stop_index"]]

    latitude = bus["latitude"]
    longitude = bus["longitude"]
    target_latitude = next_stop["latitude"]
    target_longitude = next_stop["longitude"]

    # Approximate the distance to the stop in meters.
    latitude_distance = (target_latitude - latitude) * METERS_PER_DEGREE
    longitude_distance = (
        (target_longitude - longitude)
        * METERS_PER_DEGREE
        * math.cos(math.radians(latitude))
    )
    distance = math.hypot(latitude_distance, longitude_distance)

    # Speed is in km/h; convert it to the distance traveled this update.
    travel_distance = bus["speed"] * 1000 / 3600 * UPDATE_INTERVAL_SECONDS

    if distance <= travel_distance:
        # Snap to the stop, then target the following stop on the next update.
        bus["latitude"] = target_latitude
        bus["longitude"] = target_longitude
        bus["next_stop_index"] = (bus["next_stop_index"] + 1) % len(stops)
    else:
        fraction = travel_distance / distance
        bus["latitude"] += (target_latitude - latitude) * fraction
        bus["longitude"] += (target_longitude - longitude) * fraction

    return bus


# Create 100 buses once
buses = []

for i in range(100):
    bus = create_bus(f"B{i:03d}", i)
    buses.append(bus)


# Continuously generate events
while True:

    for bus in buses:

        update_bus(bus)

        event = {
            "bus_id": bus["bus_id"],
            "route": bus["route"],
            "speed": bus["speed"],
            "latitude": bus["latitude"],
            "longitude": bus["longitude"],
            "timestamp": datetime.now().isoformat()
        }

        # Send event to Kafka
        producer.send("bus-events", value=event)

    # Make sure events are sent
    producer.flush()

    print("100 bus events sent to Kafka")

    time.sleep(UPDATE_INTERVAL_SECONDS)
