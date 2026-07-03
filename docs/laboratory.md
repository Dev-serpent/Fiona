# Laboratory User Guide

The Fiona Laboratory provides a complete IoT simulation environment
either inside GNS3 or as standalone Docker containers.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Used for the lab launcher script |
| Docker | 24+ | Needed for simulated device nodes |
| GNS3 Server | 2.2+ | Only if using the GNS3-based lab |
| GNS3 Client | — | Installed as part of Fiona (`GNS3Automation`) |

---

## Quick Start — GNS3 Lab

```bash
# 1. Ensure GNS3 server is running on localhost:3080

# 2. Launch the lab (creates project, adds nodes, starts them, discovers devices)
python -m Laboratory --auto-start --discover

# 3. View the topology in the GNS3 GUI
```

Expected output:
```
✅ Lab 'Fiona IoT Lab' ready!
   Project ID: 8a3f7e2c-...
   Nodes:      10
   Auto-start: True
   Discovered: 9 devices
```

### Command-line options

```
python -m Laboratory [OPTIONS]

Options:
  --gns3-host HOST    GNS3 server hostname (default: 127.0.0.1)
  --gns3-port PORT    GNS3 server port (default: 3080)
  --auto-start        Start all nodes after creating the topology
  --discover          Register devices with the HomeBackend API
  --verbose, -v       Enable debug logging
```

---

## Quick Start — Standalone Docker (no GNS3)

```bash
# Start all simulated devices + Mosquitto broker
docker compose -f Laboratory/docker-compose.lab.yml up -d

# Tail the logs
docker compose -f Laboratory/docker-compose.lab.yml logs -f

# Stop everything
docker compose -f Laboratory/docker-compose.lab.yml down
```

---

## Topology Reference

| Node | Type | Simulates | MQTT Topic |
|------|------|-----------|------------|
| `mqtt-broker` | Mosquitto 2 | Message broker | — |
| `living-room-light` | Alpine + Python | Smart light | `fiona/living-room-light/#` |
| `bedroom-light` | Alpine + Python | Smart light | `fiona/bedroom-light/#` |
| `kitchen-switch` | Alpine + Python | Smart switch | `fiona/kitchen-switch/#` |
| `garage-plug` | Alpine + Python | Smart plug | `fiona/garage-plug/#` |
| `hallway-motion` | Alpine + Python | Motion sensor | `fiona/hallway-motion/#` |
| `outdoor-temp` | Alpine + Python | Temperature sensor | `fiona/outdoor-temp/#` |
| `basement-humidity` | Alpine + Python | Humidity sensor | `fiona/basement-humidity/#` |
| `front-door` | Alpine + Python | Door sensor | `fiona/front-door/#` |
| `living-room-thermostat` | Alpine + Python | Thermostat | `fiona/living-room-thermostat/#` |

### MQTT Topic Hierarchy

```
fiona/{device_id}/command       ← Subscribe (control device)
fiona/{device_id}/state         ← Publish (device reports state)
fiona/{device_id}/event          ← Publish (device reports event)
fiona/{device_id}/available     ← Publish (LWT — online/offline)
```

---

## Simulation Behavior

### Lights (`light_sim.py`)
- Listens for state commands via MQTT.
- Accepts: `power` (bool), `brightness` (0–100), `color_temp` (2000–6500K), `color` (hex).
- Publishes state on change.

### Sensors (`sensor_sim.py`)
- Publishes readings at a configurable interval (default 30s).
- **Temperature**: Random walk between 15–40°C, drift ±0.5°C.
- **Humidity**: Random walk between 20–90%, drift ±2%.
- **Motion**: Random boolean, 30% chance of `true`.
- **Door**: Random boolean, 10% chance of `true`.
- **Thermostat**: Random walk between 18–28°C, drift ±0.3°C. Accepts `hvac_mode` and `target_temperature` commands.

### Switches/Plugs (`switch_sim.py`)
- Listens for `power` commands via MQTT.
- Publishes state on change.

---

## HomeBackend Integration

After the lab is running, start the HomeBackend service:

```bash
# From the project root:
python -m HomeBackend
```

This starts:
- REST API on `http://localhost:8080`
- WebSocket on `ws://localhost:8080/ws`
- MQTT client connected to `mqtt-broker:1883`

### With Docker Compose (full stack):

```bash
docker compose up -d
```

This starts HomeBackend + Mosquitto.
Then add the simulated devices via Docker Compose:

```bash
docker compose -f Laboratory/docker-compose.lab.yml up -d
```

---

## Troubleshooting

### GNS3 connection refused

```
ERROR: Failed to create project: GNS3 request failed: GET /projects: ...
```

- Ensure GNS3 server is running: `systemctl status gns3`
- Check the host/port: `curl http://localhost:3080/v2/version`
- Verify GNS3 REST API is enabled in Preferences → Server → Enable API

### Nodes fail to create

```
WARNING: Failed to add node bedroom-light: GNS3 error
```

- This is normal if nodes already exist; the lab falls back to listing them.
- Check the GNS3 GUI to see if nodes are already present.

### Device discovery warnings

```
WARNING: Failed to register living-room-light: 500 Server error
```

- The HomeBackend service may not be running.
- Start it: `python -m HomeBackend` or `docker compose up -d`.

### Custom Docker image

To build the simulation node image manually:

```bash
docker build -t fiona/sim-node:latest \
  -f Laboratory/docker/Dockerfile.simnode \
  Laboratory/devices/
```

Then reference `fiona/sim-node:latest` in your own topologies.
