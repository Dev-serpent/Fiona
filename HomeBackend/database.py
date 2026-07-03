"""SQLite-backed persistence for the HomeBackend service."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from aiohttp import web

from SmartHome.errors import DeviceNotFoundError
from SmartHome.models import (
    DeviceEvent,
    DeviceInfo,
    DeviceProperties,
    DeviceState,
    DeviceStatus,
    DeviceType,
    Room,
    Scene,
)

logger = logging.getLogger(__name__)

# Application key used to store the Database instance on the aiohttp app.
# Access via ``request.app[DB_APP_KEY]``.
DB_APP_KEY = web.AppKey("db", "Database")

# ── Serialisation helpers ─────────────────────────────────────────────────────


def _dt_to_iso(dt: datetime | None) -> str | None:
    """Convert a datetime to ISO-8601 string, or *None*."""
    if dt is None:
        return None
    return dt.isoformat()


def _iso_to_dt(value: str | None) -> datetime | None:
    """Convert an ISO-8601 string back to a datetime, or *None*."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _device_info_to_row(info: DeviceInfo) -> dict[str, Any]:
    """Flatten a ``DeviceInfo`` into a dict suitable for SQL insertion."""
    return {
        "device_id": info.device_id,
        "device_type": info.device_type.value,
        "status": info.status.value,
        "properties": json.dumps({
            "name": info.properties.name,
            "room": info.properties.room,
            "location": info.properties.location,
            "manufacturer": info.properties.manufacturer,
            "model": info.properties.model,
            "firmware_version": info.properties.firmware_version,
            "poll_interval": info.properties.poll_interval,
        }),
        "state": json.dumps({
            "power": info.state.power,
            "brightness": info.state.brightness,
            "color_temp": info.state.color_temp,
            "color": info.state.color,
            "temperature": info.state.temperature,
            "humidity": info.state.humidity,
            "motion_detected": info.state.motion_detected,
            "door_open": info.state.door_open,
            "target_temperature": info.state.target_temperature,
            "hvac_mode": info.state.hvac_mode,
        }),
        "last_seen": _dt_to_iso(info.last_seen),
        "created_at": _dt_to_iso(info.created_at),
        "tags": json.dumps(info.tags),
    }


def _row_to_device_info(row: sqlite3.Row) -> DeviceInfo:
    """Reconstruct a ``DeviceInfo`` from a SQLite row."""
    try:
        device_type = DeviceType(row["device_type"])
    except ValueError:
        device_type = DeviceType.SWITCH

    try:
        status = DeviceStatus(row["status"])
    except ValueError:
        status = DeviceStatus.UNKNOWN

    props_raw = json.loads(row["properties"])
    properties = DeviceProperties(
        name=props_raw.get("name", ""),
        room=props_raw.get("room", "default"),
        location=props_raw.get("location", ""),
        manufacturer=props_raw.get("manufacturer", "Fiona IoT"),
        model=props_raw.get("model", "v1"),
        firmware_version=props_raw.get("firmware_version", "1.0.0"),
        poll_interval=props_raw.get("poll_interval", 60),
    )

    state_raw = json.loads(row["state"]) if row["state"] else {}
    state = DeviceState(
        power=state_raw.get("power"),
        brightness=state_raw.get("brightness"),
        color_temp=state_raw.get("color_temp"),
        color=state_raw.get("color"),
        temperature=state_raw.get("temperature"),
        humidity=state_raw.get("humidity"),
        motion_detected=state_raw.get("motion_detected"),
        door_open=state_raw.get("door_open"),
        target_temperature=state_raw.get("target_temperature"),
        hvac_mode=state_raw.get("hvac_mode"),
    )

    return DeviceInfo(
        device_id=row["device_id"],
        device_type=device_type,
        status=status,
        properties=properties,
        state=state,
        last_seen=_iso_to_dt(row["last_seen"]),
        created_at=_iso_to_dt(row["created_at"]) or datetime.now(timezone.utc),
        tags=json.loads(row["tags"]) if row["tags"] else [],
    )


# ── Database ──────────────────────────────────────────────────────────────────


class Database:
    """SQLite-backed persistence for the HomeBackend service.

    Provides CRUD operations for devices, rooms, scenes, and events.
    Use as a context manager or call :meth:`connect` / :meth:`close` explicitly.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        device_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'offline',
        properties TEXT NOT NULL DEFAULT '{}',
        state TEXT NOT NULL DEFAULT '{}',
        last_seen TEXT,
        created_at TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS rooms (
        room_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        floor TEXT DEFAULT '1',
        device_ids TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS scenes (
        scene_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        states TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_events_device ON events(device_id);
    CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
    CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp);
    """

    def __init__(self, db_path: str, wal_mode: bool = True) -> None:
        """Initialise the database manager.

        Args:
            db_path: Filesystem path for the SQLite database file.
            wal_mode: Enable Write-Ahead Logging for better concurrency.
        """
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._wal_mode = wal_mode
        self._conn: Optional[sqlite3.Connection] = None

    # ── Connection lifecycle ──────────────────────────────────────────────

    def connect(self) -> None:
        """Open the database connection and create tables if needed."""
        self._conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        if self._wal_mode:
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()
        logger.info("Database connected at %s", self._db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    @property
    def is_connected(self) -> bool:
        """``True`` when the database connection is open."""
        return self._conn is not None

    # ── Context manager ───────────────────────────────────────────────────

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Yield a database cursor with automatic commit/rollback.

        If an exception is raised the transaction is rolled back; otherwise it
        is committed on exit.
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # ── Device CRUD ───────────────────────────────────────────────────────

    def create_device(self, info: DeviceInfo) -> DeviceInfo:
        """Persist a new device. Returns the stored ``DeviceInfo``."""
        row = _device_info_to_row(info)
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO devices
                   (device_id, device_type, status, properties, state,
                    last_seen, created_at, tags)
                   VALUES (:device_id, :device_type, :status, :properties, :state,
                           :last_seen, :created_at, :tags)""",
                row,
            )
        logger.info("Device created: %s (%s)", info.device_id, info.device_type.value)
        return info

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Retrieve a device by its ID. Returns ``None`` if not found."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_device_info(row)

    def list_devices(
        self,
        device_type: Optional[str] = None,
        room: Optional[str] = None,
    ) -> list[DeviceInfo]:
        """List devices, optionally filtering by type and/or room name."""
        query = "SELECT * FROM devices WHERE 1=1"
        params: list[Any] = []

        if device_type is not None:
            query += " AND device_type = ?"
            params.append(device_type)
        if room is not None:
            query += " AND json_extract(properties, '$.room') = ?"
            params.append(room)

        query += " ORDER BY created_at ASC"

        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_row_to_device_info(r) for r in rows]

    def update_device(self, device_id: str, **kwargs: Any) -> Optional[DeviceInfo]:
        """Update device fields. Returns the updated device or ``None``.

        Acceptable keyword arguments match the column names in the devices
        table (e.g. ``status``, ``properties``, ``state``, ``tags``, etc.).
        """
        allowed = {"device_type", "status", "properties", "state", "last_seen", "tags"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_device(device_id)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [device_id]

        with self._cursor() as cur:
            cur.execute(
                f"UPDATE devices SET {set_clause} WHERE device_id = ?",
                params,
            )
        return self.get_device(device_id)

    def delete_device(self, device_id: str) -> bool:
        """Remove a device by ID. Returns ``True`` if a row was deleted."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
            deleted = cur.rowcount > 0
        if deleted:
            logger.info("Device deleted: %s", device_id)
        return deleted

    def update_device_state(
        self,
        device_id: str,
        state: DeviceState,
    ) -> Optional[DeviceInfo]:
        """Update only the state of a device. Returns the updated device."""
        state_json = json.dumps({
            "power": state.power,
            "brightness": state.brightness,
            "color_temp": state.color_temp,
            "color": state.color,
            "temperature": state.temperature,
            "humidity": state.humidity,
            "motion_detected": state.motion_detected,
            "door_open": state.door_open,
            "target_temperature": state.target_temperature,
            "hvac_mode": state.hvac_mode,
        })
        return self.update_device(device_id, state=state_json)

    # ── Room CRUD ─────────────────────────────────────────────────────────

    def create_room(self, room: Room) -> Room:
        """Persist a new room."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO rooms (room_id, name, floor, device_ids)
                   VALUES (?, ?, ?, ?)""",
                (room.room_id, room.name, room.floor, json.dumps(room.device_ids)),
            )
        logger.info("Room created: %s (%s)", room.room_id, room.name)
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        """Retrieve a room by ID. Returns ``None`` if not found."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return Room(
            room_id=row["room_id"],
            name=row["name"],
            floor=row["floor"],
            device_ids=json.loads(row["device_ids"]) if row["device_ids"] else [],
        )

    def list_rooms(self) -> list[Room]:
        """Return all rooms."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM rooms ORDER BY name ASC")
            rows = cur.fetchall()
        return [
            Room(
                room_id=r["room_id"],
                name=r["name"],
                floor=r["floor"],
                device_ids=json.loads(r["device_ids"]) if r["device_ids"] else [],
            )
            for r in rows
        ]

    def assign_device_to_room(self, device_id: str, room_id: str) -> bool:
        """Add a device ID to a room's device list. Returns ``True`` on success."""
        room = self.get_room(room_id)
        if room is None:
            return False
        if device_id not in room.device_ids:
            room.device_ids.append(device_id)
        with self._cursor() as cur:
            cur.execute(
                "UPDATE rooms SET device_ids = ? WHERE room_id = ?",
                (json.dumps(room.device_ids), room_id),
            )
        return True

    def delete_room(self, room_id: str) -> bool:
        """Remove a room by ID. Returns ``True`` if a row was deleted."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM rooms WHERE room_id = ?", (room_id,))
            return cur.rowcount > 0

    # ── Scene CRUD ────────────────────────────────────────────────────────

    def create_scene(self, scene: Scene) -> Scene:
        """Persist a new scene."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO scenes (scene_id, name, states, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    scene.scene_id,
                    scene.name,
                    json.dumps(scene.states),
                    _dt_to_iso(scene.created_at),
                ),
            )
        logger.info("Scene created: %s (%s)", scene.scene_id, scene.name)
        return scene

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        """Retrieve a scene by ID. Returns ``None`` if not found."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM scenes WHERE scene_id = ?", (scene_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return Scene(
            scene_id=row["scene_id"],
            name=row["name"],
            states=json.loads(row["states"]) if row["states"] else {},
            created_at=_iso_to_dt(row["created_at"]) or datetime.now(timezone.utc),
        )

    def list_scenes(self) -> list[Scene]:
        """Return all scenes."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM scenes ORDER BY created_at ASC")
            rows = cur.fetchall()
        return [
            Scene(
                scene_id=r["scene_id"],
                name=r["name"],
                states=json.loads(r["states"]) if r["states"] else {},
                created_at=_iso_to_dt(r["created_at"]) or datetime.now(timezone.utc),
            )
            for r in rows
        ]

    def delete_scene(self, scene_id: str) -> bool:
        """Remove a scene by ID. Returns ``True`` if a row was deleted."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM scenes WHERE scene_id = ?", (scene_id,))
            return cur.rowcount > 0

    # ── Events ────────────────────────────────────────────────────────────

    def store_event(self, event: DeviceEvent) -> None:
        """Persist a device event."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO events (event_id, device_id, event_type, timestamp, data)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.device_id,
                    event.event_type,
                    _dt_to_iso(event.timestamp),
                    json.dumps(event.data),
                ),
            )

    def list_events(
        self,
        device_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[DeviceEvent]:
        """Return recent events, optionally filtered by device."""
        query = "SELECT * FROM events"
        params: list[Any] = []
        if device_id is not None:
            query += " WHERE device_id = ?"
            params.append(device_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [
            DeviceEvent(
                event_id=r["event_id"],
                device_id=r["device_id"],
                event_type=r["event_type"],
                timestamp=_iso_to_dt(r["timestamp"]) or datetime.now(timezone.utc),
                data=json.loads(r["data"]) if r["data"] else {},
            )
            for r in rows
        ]

    def clear_events(self) -> int:
        """Delete all events. Returns the number of deleted rows."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM events")
            count = cur.rowcount
        logger.info("Cleared %d events", count)
        return count
