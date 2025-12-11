"""Sensor platform for zonal_heating integration - diagnostic sensors."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_ROOMS, CONF_ZONES, DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 10  # seconds


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zonal heating diagnostic sensors from a config entry."""
    zones = entry.data.get(CONF_ZONES, [])

    entities = []
    for zone_idx, zone in enumerate(zones):
        zone_name = zone.get("name", f"Zone {zone_idx}")

        # Create zone diagnostic sensor
        entities.append(
            ZoneDiagnosticSensor(
                hass=hass,
                entry_id=entry.entry_id,
                zone_name=zone_name,
            )
        )

        # Create room diagnostic sensors
        for room_idx, room in enumerate(zone.get(CONF_ROOMS, [])):
            room_name = room.get("name", f"Room {room_idx}")
            entities.append(
                RoomDiagnosticSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_name=zone_name,
                    room_name=room_name,
                )
            )

    async_add_entities(entities)
    _LOGGER.info(
        "Zonal heating: Created %d diagnostic sensors for entry %s",
        len(entities),
        entry.entry_id,
    )


class ZoneDiagnosticSensor(SensorEntity):
    """Diagnostic sensor for a heating zone."""

    _attr_should_poll = False
    _attr_icon = "mdi:thermostat"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the zone diagnostic sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._zone_name = zone_name

        self._attr_unique_id = f"{entry_id}_{zone_name.lower().replace(' ', '_')}_diagnostic"
        self._attr_name = f"Zonal Heating {zone_name} Status"

        self._unsub_update = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Update periodically
        from datetime import timedelta
        self._unsub_update = async_track_time_interval(
            self.hass,
            self._async_scheduled_update,
            timedelta(seconds=UPDATE_INTERVAL),
        )

        # Initial update
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsub_update:
            self._unsub_update()

    @callback
    def _async_scheduled_update(self, now: datetime) -> None:
        """Handle scheduled update."""
        self._update_state()
        self.async_write_ha_state()

    def _get_zone_coordinator(self):
        """Get the zone state machine."""
        if DOMAIN not in self.hass.data:
            return None
        if self._entry_id not in self.hass.data[DOMAIN]:
            return None
        coordinators = self.hass.data[DOMAIN][self._entry_id].get("coordinators", {})
        return coordinators.get(self._zone_name)

    def _update_state(self) -> None:
        """Update the sensor state."""
        coordinator = self._get_zone_coordinator()
        if not coordinator:
            self._attr_native_value = "unavailable"
            return

        # Determine primary state
        if coordinator.away_mode and not coordinator._away_mode_timer:
            self._attr_native_value = "away_mode"
        elif coordinator._away_mode_pending:
            self._attr_native_value = "away_pending"
        elif coordinator._zone_is_on:
            self._attr_native_value = "heating"
        else:
            self._attr_native_value = "idle"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes."""
        coordinator = self._get_zone_coordinator()
        if not coordinator:
            return {"error": "Zone coordinator not found"}

        # Calculate time since last change
        time_since_change = None
        time_until_cycle_allowed = None
        cycle_time_blocking = False

        if coordinator._last_zone_change:
            elapsed = (datetime.now() - coordinator._last_zone_change).total_seconds() / 60
            time_since_change = round(elapsed, 1)

            if elapsed < coordinator.min_cycle_time:
                time_until_cycle_allowed = round(coordinator.min_cycle_time - elapsed, 1)
                cycle_time_blocking = True

        # Count rooms needing heat
        rooms_needing_heat = []
        rooms_not_needing_heat = []

        for room in coordinator.rooms:
            room_info = {
                "name": room.room_name,
                "needs_heat": room.needs_heat,
                "current_temp": room._current_temp,
                "target_temp": room._target_temp,
                "deficit": round(room.temperature_deficit, 2) if room.temperature_deficit else 0,
                "is_on": room._is_on,
                "window_open": room._window_open,
                "window_confirmed": room._window_open_confirmed,
                "overheated": room._overheated,
            }

            if room.needs_heat and room.temperature_deficit > 0:
                rooms_needing_heat.append(room_info)
            else:
                rooms_not_needing_heat.append(room_info)

        # Build reason explanation
        reason = self._build_reason(coordinator, rooms_needing_heat, cycle_time_blocking)

        # Check if in startup grace period
        in_startup_grace = coordinator._is_in_startup_grace_period() if hasattr(coordinator, '_is_in_startup_grace_period') else False

        attrs = {
            "zone_climate": coordinator.zone_climate,
            "zone_is_on": coordinator._zone_is_on,
            "zone_current_temp": coordinator._zone_current_temp,
            "min_cycle_time_minutes": coordinator.min_cycle_time,
            "time_since_last_change_minutes": time_since_change,
            "time_until_cycle_allowed_minutes": time_until_cycle_allowed,
            "cycle_time_blocking": cycle_time_blocking and not in_startup_grace,
            "startup_grace_period": in_startup_grace,
            "retry_timer_active": coordinator._retry_timer is not None,
            "rooms_total": len(coordinator.rooms),
            "rooms_needing_heat_count": len(rooms_needing_heat),
            "rooms_needing_heat": [r["name"] for r in rooms_needing_heat],
            "away_mode": coordinator._away_mode,
            "away_mode_pending": coordinator._away_mode_pending,
            "away_mode_delay": coordinator.away_mode_delay,
            "people_home": coordinator._people_home_count,
            "people_tracked": len(coordinator.person_entities),
            "reason": reason,
            "detailed_rooms": rooms_needing_heat + rooms_not_needing_heat,
        }

        return attrs

    def _build_reason(self, coordinator, rooms_needing_heat: list, cycle_blocking: bool) -> str:
        """Build a human-readable reason for current state."""
        if coordinator._away_mode and not coordinator._away_mode_timer:
            return "Away mode active - all people away"

        if coordinator._away_mode_pending:
            return f"Away mode pending - waiting {coordinator.away_mode_delay} minute delay"

        if not rooms_needing_heat:
            return "No rooms need heat - all at or above target temperature"

        if coordinator._zone_is_on:
            room_names = [r["name"] for r in rooms_needing_heat]
            return f"Heating active - {len(rooms_needing_heat)} room(s) need heat: {', '.join(room_names)}"

        if cycle_blocking:
            return f"Would turn on but min_cycle_time blocking ({coordinator.min_cycle_time} min cooldown)"

        # Zone should be on but isn't
        return f"Zone OFF but {len(rooms_needing_heat)} room(s) requesting heat - check zone thermostat"


class RoomDiagnosticSensor(SensorEntity):
    """Diagnostic sensor for a room."""

    _attr_should_poll = False
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_name: str,
        room_name: str,
    ) -> None:
        """Initialize the room diagnostic sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._zone_name = zone_name
        self._room_name = room_name

        self._attr_unique_id = f"{entry_id}_{room_name.lower().replace(' ', '_')}_diagnostic"
        self._attr_name = f"Zonal Heating {room_name} Status"

        self._unsub_update = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        from datetime import timedelta
        self._unsub_update = async_track_time_interval(
            self.hass,
            self._async_scheduled_update,
            timedelta(seconds=UPDATE_INTERVAL),
        )

        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsub_update:
            self._unsub_update()

    @callback
    def _async_scheduled_update(self, now: datetime) -> None:
        """Handle scheduled update."""
        self._update_state()
        self.async_write_ha_state()

    def _get_room_state_machine(self):
        """Get the room state machine."""
        if DOMAIN not in self.hass.data:
            return None
        if self._entry_id not in self.hass.data[DOMAIN]:
            return None
        coordinators = self.hass.data[DOMAIN][self._entry_id].get("coordinators", {})
        zone_coordinator = coordinators.get(self._zone_name)
        if not zone_coordinator:
            return None

        for room in zone_coordinator.rooms:
            if room.room_name == self._room_name:
                return room
        return None

    def _update_state(self) -> None:
        """Update the sensor state."""
        room = self._get_room_state_machine()
        if not room:
            self._attr_native_value = "unavailable"
            return

        # Determine primary state
        if room._overheated:
            self._attr_native_value = "overheated"
        elif room._window_open_confirmed:
            self._attr_native_value = "window_open"
        elif room.needs_heat:
            self._attr_native_value = "needs_heat"
        elif not room._is_on:
            self._attr_native_value = "off"
        else:
            self._attr_native_value = "satisfied"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes."""
        room = self._get_room_state_machine()
        if not room:
            return {"error": "Room state machine not found"}

        # Build reason explanation
        reason = self._build_reason(room)

        attrs = {
            "climate_entity": room.climate_entity,
            "current_temp": room._current_temp,
            "target_temp": room._target_temp,
            "temp_differential": room.temp_differential,
            "overheat_threshold": room.overheat_threshold,
            "temperature_deficit": round(room.temperature_deficit, 2) if room.temperature_deficit else 0,
            "needs_heat": room.needs_heat,
            "is_on": room._is_on,
            "window_open": room._window_open,
            "window_open_confirmed": room._window_open_confirmed,
            "window_timer_active": room._window_timer is not None,
            "overheated": room._overheated,
            "reason": reason,
        }

        # Add overheat limit calculation
        if room._target_temp is not None:
            attrs["overheat_limit"] = round(room._target_temp + room.overheat_threshold, 1)
            attrs["heat_threshold"] = round(room._target_temp - room.temp_differential, 1)

        return attrs

    def _build_reason(self, room) -> str:
        """Build a human-readable reason for current state."""
        if not room._is_on:
            return "Climate entity is OFF"

        if room._overheated:
            overheat_limit = room._target_temp + room.overheat_threshold
            return f"Overheated - current {room._current_temp:.1f}C >= limit {overheat_limit:.1f}C"

        if room._window_open_confirmed:
            return "Window confirmed open - heating paused"

        if room._window_open:
            return f"Window detected open - waiting {room.window_delay}s delay to confirm"

        if room._current_temp is None or room._target_temp is None:
            return "Missing temperature data"

        threshold = room._target_temp - room.temp_differential
        if room._current_temp < threshold:
            return f"Needs heat - current {room._current_temp:.1f}C < threshold {threshold:.1f}C"

        return f"Satisfied - current {room._current_temp:.1f}C >= threshold {threshold:.1f}C"
