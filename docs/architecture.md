# Fiona IoT HomeBackend — Architecture

## System Overview

Fiona's IoT subsystem consists of four packages that form a layered
architecture:

```
┌──────────────────────────────────────────────────────────────────┐
│                        Laboratory                                │
│  (Pre-built GNS3 topology, simulation scripts, lab launcher)     │
├──────────────────────────────────────────────────────────────────┤
│                       GNS3Automation                             │
│  (Async REST client, project/topology manager, device discovery) │
├──────────────────────────────────────────────────────────────────┤
│                        HomeBackend                               │
│  (aiohttp REST API + WebSocket, SQLite, MQTT client, broker)     │
├──────────────────────────────────────────────────────────────────┤
│                        SmartHome                                 │
│  (Models, interfaces, errors, config, events, device drivers,    │
│   registry, conditions, actions, rules, automation engine)       │
└──────────────────────────────────────────────────────────────────┘
```

## Layer Descriptions

### SmartHome — Foundation

The **only** package that other packages must depend on.  It defines:

- **Models**: `DeviceType`, `DeviceStatus`, `DeviceState`, `DeviceInfo`,
  `DeviceEvent`, `Room`, `Scene` — used across all layers for type safety.
- **Interfaces**: `IDeviceDriver`, `IAutomationEngine`, `ICondition`,
  `IAction` — plug-in contracts.
- **Errors**: `SmartHomeError`, `DeviceError`, `RegistryError`, etc.
- **Config**: `SmartHomeConfig` dataclass.
- **Events**: `EventBus` — pub/sub for state changes.
- **Device Drivers**: 8 concrete drivers (`LightDriver`, `SwitchDriver`,
  `PlugDriver`, `MotionSensorDriver`, `TemperatureSensorDriver`,
  `HumiditySensorDriver`, `DoorSensorDriver`, `ThermostatDriver`) plus
  `DeviceRegistry` (in-memory with optional SQLite persistence).
- **Automation**: Composable conditions, pluggable actions,
  `StateChangeRule`, `ScheduleRule`, `AutomationEngine`.

### HomeBackend — Service Layer

An aiohttp-based HTTP service that exposes the system:

- **REST API**: CRUD for devices, rooms, scenes, events, health checks.
- **WebSocket**: Real-time event push.
- **MQTT Client**: Bidirectional sync with physical/simulated devices.
- **SQLite Database**: Persistent storage via `aiosqlite`.
- **Docker**: Multi-stage `Dockerfile` + `docker-compose.yml` with Mosquitto.

All route handlers access the database through a shared `AppKey("db", ...)`,
imported consistently from `HomeBackend.database`.

### GNS3Automation — Integration Layer

An async REST client for the GNS3 v2 API:

- **Client**: Low-level HTTP wrapper with auth, timeout, error mapping.
- **ProjectManager**: High-level CRUD + open/close lifecycle.
- **TopologyBuilder**: Node/link management within a project.
- **Templates**: Docker image presets (Alpine, Python IoT sensor, Mosquitto).
- **Discovery**: Map GNS3 node names to `SmartHome` device types.
- **Models**: Dataclasses for `GNS3Project`, `GNS3Node`, `GNS3Link`,
  `GNS3Template`.
- **Errors**: 7 GNS3-specific exception classes.

### Laboratory — Built-in Lab

A turnkey GNS3 laboratory for development and demonstration:

- **Topology**: 10-node sample network (1 Mosquitto broker + 9 IoT devices).
- **Simulation Scripts**: Python MQTT clients that mimic real devices.
- **Launcher**: `python -m Laboratory` — one-command project setup.
- **Docker Compose**: Standalone lab without GNS3.

## Data Flow

### State Change (Device → UI)

```
IoT Device → MQTT Broker → HomeBackend MQTT Client
    → Device Registry (update state)
    → EventBus → WebSocket → Browser
    → Automation Engine (evaluate rules)
```

### Command (UI → Device)

```
Browser → REST API → HomeBackend Route Handler
    → Device Registry (update state)
    → EventBus → MQTT Client → MQTT Broker → IoT Device
    → Automation Engine (evaluate rules)
```

### Lab Provisioning (GNS3)

```
python -m Laboratory → GNS3Automation Client
    → GNS3 REST API → Create project
    → Add Docker nodes (broker + devices)
    → Create network links
    → Start nodes (optional)
    → Discover & register with HomeBackend (optional)
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Virtual mode by default** | All device drivers work without hardware — `connect()` succeeds with no I/O.  Enables testing and development on any machine. |
| **SmartHome has zero dependencies** | The foundation layer imports only stdlib.  Optional extras (paho-mqtt) are declared in `pyproject.toml`. |
| **GNS3Config-driven connection** | Every aspect of the GNS3 connection (host, port, auth, SSL, timeout) is configured through a single dataclass or environment variables. |
| **AppKey-based DI** | `web.AppKey("db", ...)` is used consistently across all route files instead of string keys, preventing subtle runtime errors. |
| **aioresponses for test isolation** | All GNS3 HTTP tests use `aioresponses` — no real GNS3 server needed for CI. |
