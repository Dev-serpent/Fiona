# HomeBackend REST API Reference

Base URL: `http://localhost:8080`

Content-Type: `application/json`

Error format:
```json
{
    "error": "Error message string"
}
```

---

## Devices

### List Devices

```
GET /api/devices
```

Query parameters:
- `type` — Filter by device type (e.g., `light`, `motion_sensor`)
- `room` — Filter by room ID

Response: `200` — Array of device objects.

### Get Device

```
GET /api/devices/{device_id}
```

Response: `200` — Device object.
Error: `404` — Device not found.

### Create Device

```
POST /api/devices
```

Request body:
```json
{
    "device_id": "living-room-light",
    "name": "Living Room Light",
    "device_type": "light",
    "room": "living-room"
}
```

Response: `201` — Created device object.
Error: `400` — Invalid device type or empty body.

### Update Device

```
PUT /api/devices/{device_id}
```

Request body — partial update:
```json
{
    "name": "Updated Name",
    "room": "bedroom"
}
```

Response: `200` — Updated device object.
Error: `404` — Device not found.

### Delete Device

```
DELETE /api/devices/{device_id}
```

Response: `204` — No content.
Error: `404` — Device not found.

### Update Device State

```
PUT /api/devices/{device_id}/state
```

Request body:
```json
{
    "power": true,
    "brightness": 80
}
```

Response: `200` — Updated device object with new state.

---

## Rooms

### List Rooms

```
GET /api/rooms
```

Response: `200` — Array of room objects.

### Get Room

```
GET /api/rooms/{room_id}
```

Includes an array of devices belonging to the room.

Response: `200` — Room object with `devices` array.
Error: `404` — Room not found.

### Create Room

```
POST /api/rooms
```

Request body:
```json
{
    "room_id": "living-room",
    "name": "Living Room"
}
```

Response: `201` — Created room object.
Error: `400` — Empty body.

### Update Room

```
PUT /api/rooms/{room_id}
```

Request body — partial update:
```json
{
    "name": "Updated Name"
}
```

Response: `200` — Updated room object.
Error: `404` — Room not found.

### Delete Room

```
DELETE /api/rooms/{room_id}
```

Response: `204` — No content.
Error: `404` — Room not found.

---

## Scenes

### List Scenes

```
GET /api/scenes
```

Response: `200` — Array of scene objects.

### Get Scene

```
GET /api/scenes/{scene_id}
```

Response: `200` — Scene object.
Error: `404` — Scene not found.

### Create Scene

```
POST /api/scenes
```

Request body:
```json
{
    "scene_id": "good-night",
    "name": "Good Night",
    "states": {
        "living-room-light": {"power": false},
        "bedroom-light": {"power": false}
    }
}
```

Response: `201` — Created scene object.
Error: `400` — Empty body.

### Update Scene

```
PUT /api/scenes/{scene_id}
```

Request body — partial update.

Response: `200` — Updated scene object.
Error: `404` — Scene not found.

### Delete Scene

```
DELETE /api/scenes/{scene_id}
```

Response: `204` — No content.
Error: `404` — Scene not found.

### Activate Scene

```
POST /api/scenes/{scene_id}/activate
```

Applies all device states defined in the scene.

Response: `200` — Activation confirmation.
Error: `404` — Scene not found.

---

## Events

### List Events

```
GET /api/events
```

Query parameters:
- `device_id` — Filter by device
- `event_type` — Filter by event type (e.g., `state_changed`)
- `limit` — Max results (default 100)
- `offset` — Pagination offset

Response: `200` — Array of event objects.

### Clear Events

```
DELETE /api/events
```

Response: `204` — No content.

---

## Health

### Liveness

```
GET /api/health
```

Response: `200`
```json
{
    "status": "healthy"
}
```

### Readiness

```
GET /api/ready
```

Checks that the database is accessible.

Response: `200`
```json
{
    "status": "ready"
}
```

Error: `503` — Database unavailable.

---

## WebSocket

### Connection

```
ws://localhost:8080/ws
```

### Message Format (server → client)

```json
{
    "type": "event",
    "data": {
        "device_id": "hallway-motion",
        "event_type": "state_changed",
        "data": {
            "motion_detected": true
        },
        "timestamp": "2026-07-03T12:00:00Z"
    }
}
```
