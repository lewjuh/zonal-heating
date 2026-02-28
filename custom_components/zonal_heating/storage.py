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

STORAGE_VERSION = 3
STORAGE_KEY = f"{DOMAIN}.state"


class _ZonalHeatingStore(Store):
    """Store subclass with migration support."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Migrate stored data from older versions."""
        if old_major_version < 3:
            # v1->v2 added schedules; v2->v3 removes schedules, away mode, overheat
            old_data.pop("schedules", None)
            for zone_data in old_data.get("zones", {}).values():
                zone_data.pop("away_mode_pending", None)
                zone_data.pop("away_mode_timer_remaining", None)
                zone_data.pop("pre_away_targets", None)
            for room_data in old_data.get("rooms", {}).values():
                room_data.pop("overheated", None)
                room_data.pop("trv_turned_off_for_window", None)
                room_data.pop("saved_target_temp", None)
            _LOGGER.info("Migrated storage from v%s to v3", old_major_version)
        return old_data


class ZonalHeatingStorage:
    """Handle persistent storage for zonal heating state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the storage."""
        self.hass = hass
        self.entry_id = entry_id
        self._store = _ZonalHeatingStore(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self._data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any]:
        """Load stored data."""
        data = await self._store.async_load()
        if data is None:
            data = {"zones": {}, "rooms": {}}
        self._data = data
        _LOGGER.debug("Loaded persistent state: %s", data)
        return data

    async def async_save(self) -> None:
        """Save current data to storage."""
        await self._store.async_save(self._data)
        _LOGGER.debug("Saved persistent state: %s", self._data)

    async def async_remove(self) -> None:
        """Remove stored data."""
        await self._store.async_remove()
        self._data = {"zones": {}, "rooms": {}}

    def get_zone_state(self, zone_name: str) -> dict[str, Any] | None:
        """Get stored state for a zone."""
        return self._data.get("zones", {}).get(zone_name)

    def set_zone_state(
        self,
        zone_name: str,
        zone_is_on: bool,
        last_zone_change: datetime | None,
    ) -> None:
        """Set state for a zone."""
        if "zones" not in self._data:
            self._data["zones"] = {}

        self._data["zones"][zone_name] = {
            "zone_is_on": zone_is_on,
            "last_zone_change": last_zone_change.isoformat() if last_zone_change else None,
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
    ) -> None:
        """Set state for a room."""
        if "rooms" not in self._data:
            self._data["rooms"] = {}

        self._data["rooms"][room_name] = {
            "window_open": window_open,
            "window_open_confirmed": window_open_confirmed,
            "window_timer_remaining": window_timer_remaining,
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


def parse_datetime(iso_string: str | None) -> datetime | None:
    """Parse ISO datetime string safely, always returning timezone-aware."""
    if iso_string is None:
        return None
    try:
        parsed = dt_util.parse_datetime(iso_string)
        if parsed is None:
            parsed = datetime.fromisoformat(iso_string)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed
    except (ValueError, TypeError):
        return None
