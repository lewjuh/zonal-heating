"""Persistent storage for zonal heating state machines."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 2
STORAGE_KEY = f"{DOMAIN}.state"


class ZonalHeatingStorage:
    """Handle persistent storage for zonal heating state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the storage."""
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self._data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any]:
        """Load stored data."""
        data = await self._store.async_load()
        if data is None:
            data = {"zones": {}, "rooms": {}, "schedules": {}}
        else:
            data = self._migrate_data(data)
        self._data = data
        _LOGGER.debug("Loaded persistent state: %s", data)
        return data

    def _migrate_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate data from older storage versions."""
        if "schedules" not in data:
            data["schedules"] = {}
            _LOGGER.info("Migrated storage: added schedules section")
        return data

    async def async_save(self) -> None:
        """Save current data to storage."""
        await self._store.async_save(self._data)
        _LOGGER.debug("Saved persistent state: %s", self._data)

    async def async_remove(self) -> None:
        """Remove stored data."""
        await self._store.async_remove()
        self._data = {"zones": {}, "rooms": {}, "schedules": {}}

    def get_zone_state(self, zone_name: str) -> dict[str, Any] | None:
        """Get stored state for a zone."""
        return self._data.get("zones", {}).get(zone_name)

    def set_zone_state(
        self,
        zone_name: str,
        zone_is_on: bool,
        last_zone_change: datetime | None,
        away_mode_pending: bool,
        away_mode_timer_remaining: float | None,
    ) -> None:
        """Set state for a zone."""
        if "zones" not in self._data:
            self._data["zones"] = {}

        self._data["zones"][zone_name] = {
            "zone_is_on": zone_is_on,
            "last_zone_change": last_zone_change.isoformat() if last_zone_change else None,
            "away_mode_pending": away_mode_pending,
            "away_mode_timer_remaining": away_mode_timer_remaining,
            "saved_at": dt_util.now().isoformat(),
        }

    def get_room_state(self, room_name: str) -> dict[str, Any] | None:
        """Get stored state for a room."""
        return self._data.get("rooms", {}).get(room_name)

    def set_room_state(
        self,
        room_name: str,
        window_open: bool,
        window_open_confirmed: bool,
        window_timer_remaining: float | None,
        trv_turned_off_for_window: bool,
        overheated: bool,
    ) -> None:
        """Set state for a room."""
        if "rooms" not in self._data:
            self._data["rooms"] = {}

        self._data["rooms"][room_name] = {
            "window_open": window_open,
            "window_open_confirmed": window_open_confirmed,
            "window_timer_remaining": window_timer_remaining,
            "trv_turned_off_for_window": trv_turned_off_for_window,
            "overheated": overheated,
            "saved_at": dt_util.now().isoformat(),
        }

    def clear_room_state(self, room_name: str) -> None:
        """Clear stored state for a room."""
        if "rooms" in self._data and room_name in self._data["rooms"]:
            del self._data["rooms"][room_name]

    def clear_zone_state(self, zone_name: str) -> None:
        """Clear stored state for a zone."""
        if "zones" in self._data and zone_name in self._data["zones"]:
            del self._data["zones"][zone_name]

    def get_room_schedule(self, room_name: str) -> dict[str, Any] | None:
        """Get stored schedule for a room."""
        return self._data.get("schedules", {}).get(room_name)

    def set_room_schedule(
        self,
        room_name: str,
        schedule: dict[str, Any],
    ) -> None:
        """Set schedule for a room."""
        if "schedules" not in self._data:
            self._data["schedules"] = {}

        validated = self._validate_schedule(schedule)
        self._data["schedules"][room_name] = validated
        _LOGGER.info(
            "Updated schedule for %s: enabled=%s, weekday=%d points, weekend=%d points",
            room_name,
            validated.get("enabled", True),
            len(validated.get("weekday", [])),
            len(validated.get("weekend", [])),
        )

    def delete_room_schedule(self, room_name: str) -> None:
        """Delete schedule for a room."""
        if "schedules" in self._data and room_name in self._data["schedules"]:
            del self._data["schedules"][room_name]
            _LOGGER.info("Deleted schedule for %s", room_name)

    def get_all_schedules(self) -> dict[str, Any]:
        """Get all room schedules."""
        return self._data.get("schedules", {})

    def _validate_schedule(self, schedule: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalise a schedule."""
        validated = {
            "enabled": schedule.get("enabled", True),
            "weekday": self._validate_schedule_points(schedule.get("weekday", [])),
            "weekend": self._validate_schedule_points(schedule.get("weekend", [])),
        }
        return validated

    def _validate_schedule_points(self, points: list) -> list:
        """Validate and sort schedule points."""
        valid_points = []
        for point in points:
            if self._is_valid_schedule_point(point):
                valid_points.append({
                    "time": point["time"],
                    "temperature": float(point["temperature"]),
                })
        return sorted(valid_points, key=lambda p: p["time"])

    def _is_valid_schedule_point(self, point: dict) -> bool:
        """Check if a schedule point is valid."""
        if not isinstance(point, dict):
            return False
        if "time" not in point or "temperature" not in point:
            return False
        try:
            datetime.strptime(point["time"], "%H:%M")
        except ValueError:
            return False
        try:
            temp = float(point["temperature"])
            if not 5.0 <= temp <= 30.0:
                return False
        except (ValueError, TypeError):
            return False
        return True


def parse_datetime(iso_string: str | None) -> datetime | None:
    """Parse ISO datetime string safely."""
    if iso_string is None:
        return None
    try:
        parsed = dt_util.parse_datetime(iso_string)
        if parsed is not None:
            return parsed
        return datetime.fromisoformat(iso_string)
    except (ValueError, TypeError):
        return None
