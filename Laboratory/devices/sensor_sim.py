"""Simulated IoT sensor — publishes sensor readings periodically."""
from __future__ import annotations

import argparse
import json
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

TOPIC_PREFIX = "fiona"

# Simulation ranges per sensor type
SIM_RANGES = {
    "temperature": {"min": 15.0, "max": 40.0, "drift": 0.5},
    "humidity": {"min": 20.0, "max": 90.0, "drift": 2.0},
    "motion": {"values": [True, False], "weights": [0.3, 0.7]},
    "door": {"values": [True, False], "weights": [0.1, 0.9]},
    "thermostat": {"min": 18.0, "max": 28.0, "drift": 0.3},
}


def _random_walk(current, rmin, rmax, drift):
    """Simple random-walk simulation."""
    if current is None:
        return (rmin + rmax) / 2.0
    delta = random.uniform(-drift, drift)  # noqa: DUO100
    current += delta
    return max(rmin, min(rmax, current))


def main() -> None:
    import random as _random
    global random
    random = _random

    parser = argparse.ArgumentParser(description="Simulated IoT sensor")
    parser.add_argument("--name", default="sensor", help="Sensor name/ID")
    parser.add_argument("--type", default="temperature",
                        choices=["temperature", "humidity", "motion", "door", "thermostat"],
                        help="Sensor type")
    parser.add_argument("--mqtt-host", default="mqtt-broker", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--interval", type=float, default=30.0, help="Publish interval (seconds)")
    args = parser.parse_args()

    device_id = args.name.replace(" ", "-").lower()
    sim_config = SIM_RANGES.get(args.type, SIM_RANGES["temperature"])
    current_value = None
    current_bool: bool = False

    print(f"[{device_id}] Simulated {args.type} sensor starting "
          f"(interval={args.interval}s, MQTT: {args.mqtt_host}:{args.mqtt_port})")

    if mqtt is not None:
        client = mqtt.Client(client_id=device_id)

        def on_connect(c, userdata, flags, rc) -> None:
            print(f"[{device_id}] Connected to MQTT broker (rc={rc})")
            c.publish(f"{TOPIC_PREFIX}/{device_id}/available", "online", retain=True)

        client.on_connect = on_connect
        client.will_set(
            f"{TOPIC_PREFIX}/{device_id}/available",
            "offline", retain=True,
        )

        try:
            client.connect(args.mqtt_host, args.mqtt_port, keepalive=60)
            client.loop_start()

            while True:
                if args.type in ("temperature", "humidity", "thermostat"):
                    current_value = _random_walk(
                        current_value,
                        sim_config["min"],
                        sim_config["max"],
                        sim_config["drift"],
                    )
                    payload = {args.type: round(current_value, 1)}
                else:
                    # Boolean types (motion, door)
                    current_bool = random.choices(
                        sim_config["values"],
                        weights=sim_config["weights"],
                    )[0]
                    key = "motion_detected" if args.type == "motion" else "door_open"
                    payload = {key: current_bool}

                client.publish(
                    f"{TOPIC_PREFIX}/{device_id}/state",
                    json.dumps(payload),
                )
                client.publish(
                    f"{TOPIC_PREFIX}/{device_id}/event",
                    json.dumps({"event": "sensor_reading", "data": payload}),
                )
                print(f"[{device_id}] Published: {payload}")
                time.sleep(args.interval)

        except KeyboardInterrupt:
            print(f"[{device_id}] Shutting down")
            client.publish(f"{TOPIC_PREFIX}/{device_id}/available", "offline", retain=True)
            client.loop_stop()
            client.disconnect()
    else:
        print(f"[{device_id}] Standalone mode (no MQTT)")
        try:
            while True:
                if args.type in ("temperature", "humidity", "thermostat"):
                    current_value = _random_walk(
                        current_value,
                        sim_config["min"],
                        sim_config["max"],
                        sim_config["drift"],
                    )
                    payload = {args.type: round(current_value, 1)}
                else:
                    current_bool = random.choice(sim_config["values"])
                    key = "motion_detected" if args.type == "motion" else "door_open"
                    payload = {key: current_bool}
                print(f"[{device_id}] {payload}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"[{device_id}] Shutting down")


if __name__ == "__main__":
    main()
