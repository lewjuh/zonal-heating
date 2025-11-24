"""Zone state machine for zonal heating integration."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .room_state_machine import RoomStateMachine

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)


class ZoneStateMachine:
    """State machine for managing zone heating based on room states."""

    def __init__(
        self,
        hass: HomeAssistant,
        zone_name: str,
        zone_climate: str,
        rooms: list[RoomStateMachine],
        min_cycle_time: int = 5,
    ) -> None:
        """Initialize zone state machine."""
        self.hass = hass
        self.zone_name = zone_name
        self.zone_climate = zone_climate
        self.rooms = rooms
        self.min_cycle_time = min_cycle_time

        # State tracking
        self._zone_is_on = False
        self._last_zone_change: datetime | None = None
        self._zone_current_temp: float | None = None

        # Retry timer for min_cycle_time blocking
        self._retry_timer: asyncio.TimerHandle | None = None

        # Listeners
        self._remove_listeners: list[Callable] = []

    async def async_start(self) -> None:
        """Start the zone state machine."""
        _LOGGER.info("Starting zone state machine for %s", self.zone_name)

        # Start all room state machines
        for room in self.rooms:
            await room.async_start()

        # Track zone climate changes
        self._remove_listeners.append(
            async_track_state_change_event(
                self.hass,
                [self.zone_climate],
                self._async_zone_climate_changed,
            )
        )

        # Track all room climate changes to trigger zone evaluation
        room_entities = [room.climate_entity for room in self.rooms]
        self._remove_listeners.append(
            async_track_state_change_event(
                self.hass,
                room_entities,
                self._async_room_changed,
            )
        )

        # Update zone climate state
        await self._async_update_zone_climate_state()

        # Do initial evaluation
        await self._async_evaluate_zone()

    async def async_stop(self) -> None:
        """Stop the zone state machine."""
        # Cancel any pending retry timer
        if self._retry_timer:
            self._retry_timer.cancel()
            self._retry_timer = None

        for room in self.rooms:
            await room.async_stop()

        for remove_listener in self._remove_listeners:
            remove_listener()
        self._remove_listeners.clear()

    @callback
    def _async_zone_climate_changed(self, event: Event) -> None:
        """Handle zone climate state changes."""
        self.hass.async_create_task(self._async_update_zone_climate_state())

    @callback
    def _async_room_changed(self, event: Event) -> None:
        """Handle room state changes - triggers zone evaluation."""
        entity_id = event.data.get("entity_id")
        _LOGGER.debug(
            "%s: Room climate changed (%s), triggering zone evaluation",
            self.zone_name,
            entity_id,
        )
        self.hass.async_create_task(self._async_evaluate_zone())

    async def _async_update_zone_climate_state(self) -> None:
        """Update zone climate state from entity."""
        state = self.hass.states.get(self.zone_climate)
        if not state:
            return

        self._zone_current_temp = state.attributes.get("current_temperature")
        self._zone_is_on = state.state == HVACMode.HEAT

    async def _async_evaluate_zone(self) -> None:
        """Evaluate zone state based on room states."""
        # Cancel any pending retry timer since we're evaluating now
        if self._retry_timer:
            self._retry_timer.cancel()
            self._retry_timer = None

        _LOGGER.info("=" * 60)
        _LOGGER.info("%s: ZONE EVALUATION STARTED", self.zone_name)
        _LOGGER.info("=" * 60)

        # Find rooms that need heat
        rooms_needing_heat = [
            room
            for room in self.rooms
            if room.needs_heat and room.temperature_deficit > 0
        ]

        # Log all room states
        _LOGGER.info(
            "%s: Room status - %d/%d rooms need heat",
            self.zone_name,
            len(rooms_needing_heat),
            len(self.rooms),
        )

        for room in self.rooms:
            if room.needs_heat and room.temperature_deficit > 0:
                _LOGGER.info(
                    "%s:   ✓ %s NEEDS HEAT (deficit: %.1f°C)",
                    self.zone_name,
                    room.room_name,
                    room.temperature_deficit,
                )
            else:
                _LOGGER.debug(
                    "%s:   ✗ %s does not need heat",
                    self.zone_name,
                    room.room_name,
                )

        # Determine desired zone state
        desired_zone_on = len(rooms_needing_heat) > 0

        _LOGGER.info(
            "%s: Current zone state: %s, Desired zone state: %s",
            self.zone_name,
            "ON" if self._zone_is_on else "OFF",
            "ON" if desired_zone_on else "OFF",
        )

        # Check if we should respect min cycle time
        if self._should_respect_min_cycle_time(desired_zone_on):
            return

        # Update zone climate
        await self._async_update_zone_climate(desired_zone_on, rooms_needing_heat)

    def _should_respect_min_cycle_time(self, desired_on: bool) -> bool:
        """Check if we should respect minimum cycle time."""
        # If no previous change, allow this one
        if self._last_zone_change is None:
            _LOGGER.debug("%s: No previous change, allowing action", self.zone_name)
            return False

        # If desired state matches current, no change needed
        if desired_on == self._zone_is_on:
            _LOGGER.debug(
                "%s: Zone already in desired state (%s), no change needed",
                self.zone_name,
                "ON" if self._zone_is_on else "OFF",
            )
            return False

        # Check if enough time has elapsed
        time_since_change = (
            datetime.now() - self._last_zone_change
        ).total_seconds() / 60

        if time_since_change < self.min_cycle_time:
            time_remaining = self.min_cycle_time - time_since_change
            time_remaining_seconds = time_remaining * 60

            _LOGGER.warning(
                "%s: ⏱️  MIN CYCLE TIME BLOCKING CHANGE! "
                "Would turn zone %s but only %.1f min elapsed (min: %d min, %.1f min remaining)",
                self.zone_name,
                "OFF→ON" if desired_on else "ON→OFF",
                time_since_change,
                self.min_cycle_time,
                time_remaining,
            )

            # Schedule automatic retry after min_cycle_time expires
            _LOGGER.info(
                "%s: ⏱️  Scheduling automatic retry in %.1f minutes",
                self.zone_name,
                time_remaining,
            )
            self._retry_timer = self.hass.loop.call_later(
                time_remaining_seconds,
                lambda: self.hass.async_create_task(self._async_evaluate_zone()),
            )

            return True

        _LOGGER.debug(
            "%s: Min cycle time elapsed (%.1f min), allowing change",
            self.zone_name,
            time_since_change,
        )
        return False

    async def _async_update_zone_climate(
        self, turn_on: bool, rooms_needing_heat: list[RoomStateMachine]
    ) -> None:
        """Update zone climate based on desired state."""
        # Check if zone climate entity exists
        zone_state = self.hass.states.get(self.zone_climate)
        if not zone_state:
            _LOGGER.warning(
                "%s: Zone climate %s not found", self.zone_name, self.zone_climate
            )
            return

        # Get current zone temperature
        zone_temp = zone_state.attributes.get("current_temperature")
        zone_hvac = zone_state.state

        # Determine if we need to make changes
        needs_change = (turn_on and zone_hvac != HVACMode.HEAT) or (
            not turn_on and zone_hvac == HVACMode.HEAT
        )

        if not needs_change:
            _LOGGER.debug(
                "%s: No change needed - zone already %s",
                self.zone_name,
                "ON" if turn_on else "OFF",
            )
            return

        # Log the change
        _LOGGER.info("🔥" * 30)
        _LOGGER.info(
            "%s: 🔄 CHANGING ZONE CLIMATE %s → %s",
            self.zone_name,
            "ON" if zone_hvac == HVACMode.HEAT else "OFF",
            "ON" if turn_on else "OFF",
        )
        _LOGGER.info(
            "%s: Rooms needing heat: %d", self.zone_name, len(rooms_needing_heat)
        )

        if rooms_needing_heat:
            for room in rooms_needing_heat:
                _LOGGER.info(
                    "%s:   → %s (deficit: %.1f°C)",
                    self.zone_name,
                    room.room_name,
                    room.temperature_deficit,
                )
        else:
            _LOGGER.info("%s:   No rooms need heat", self.zone_name)

        if turn_on:
            # Turn zone ON - set temperature above current to trigger boiler
            target_temp = (zone_temp + 5) if zone_temp is not None else 25
            _LOGGER.info(
                "%s: 🌡️  Setting zone temperature: %.1f°C → %.1f°C (current + 5°C)",
                self.zone_name,
                zone_temp or 0,
                target_temp,
            )

            await self.hass.services.async_call(
                "climate",
                SERVICE_SET_TEMPERATURE,
                {
                    ATTR_ENTITY_ID: self.zone_climate,
                    ATTR_TEMPERATURE: target_temp,
                },
                blocking=True,
            )
        else:
            _LOGGER.info(
                "%s: ❄️  Turning OFF - no temperature change needed", self.zone_name
            )

        # Set HVAC mode
        _LOGGER.info(
            "%s: Setting HVAC mode to %s",
            self.zone_name,
            HVACMode.HEAT if turn_on else HVACMode.OFF,
        )
        await self.hass.services.async_call(
            "climate",
            SERVICE_SET_HVAC_MODE,
            {
                ATTR_ENTITY_ID: self.zone_climate,
                "hvac_mode": HVACMode.HEAT if turn_on else HVACMode.OFF,
            },
            blocking=True,
        )

        # Update tracking
        self._zone_is_on = turn_on
        self._last_zone_change = datetime.now()

        _LOGGER.info(
            "%s: ✅ Zone change complete - now %s (min_cycle_time reset)",
            self.zone_name,
            "ON" if turn_on else "OFF",
        )
        _LOGGER.info("🔥" * 30)
