"""Zone state machine for zonal heating integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .room_state_machine import RoomStateMachine
from .storage import ZonalHeatingStorage, parse_datetime

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)


STARTUP_GRACE_PERIOD = 120  # Seconds to ignore min_cycle_time after startup


class ZoneStateMachine:
    """State machine for managing zone heating based on room states."""

    def __init__(
        self,
        hass: HomeAssistant,
        zone_name: str,
        zone_climate: str,
        rooms: list[RoomStateMachine],
        min_cycle_time: int = 5,
        storage: ZonalHeatingStorage | None = None,
    ) -> None:
        """Initialize zone state machine."""
        self.hass = hass
        self.zone_name = zone_name
        self.zone_climate = zone_climate
        self.rooms = rooms
        self.min_cycle_time = min_cycle_time
        self._storage = storage

        # State tracking
        self._zone_is_on = False
        self._last_zone_change = None
        self._zone_current_temp: float | None = None

        # Startup tracking - ignore min_cycle_time during grace period
        self._startup_time = None

        # Retry timer for min_cycle_time blocking
        self._retry_timer: asyncio.TimerHandle | None = None

        # Track if we're currently updating zone (to detect external changes)
        self._updating_zone = False

        # Periodic safety check timer
        self._periodic_timer: asyncio.TimerHandle | None = None
        self._periodic_interval = 300  # Seconds between periodic checks

        # Debounce timer for room change events
        self._eval_debounce_timer: asyncio.TimerHandle | None = None

        # Concurrency guard for zone evaluation
        self._eval_lock = asyncio.Lock()

        # Listeners
        self._remove_listeners: list[Callable] = []

    async def async_start(self) -> None:
        """Start the zone state machine."""
        _LOGGER.info("Starting zone state machine for %s", self.zone_name)

        self._startup_time = dt_util.now()

        state_restored = await self._async_restore_state()
        if state_restored:
            _LOGGER.info(
                "%s: State restored from previous session, skipping startup grace period",
                self.zone_name,
            )
        else:
            _LOGGER.info(
                "%s: Startup grace period active - min_cycle_time ignored for %d seconds",
                self.zone_name,
                STARTUP_GRACE_PERIOD,
            )

        # Start all room state machines and register callbacks
        for room in self.rooms:
            room.set_on_needs_heat_changed(self._on_room_needs_heat_changed)
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

        # Track external temperature sensors and window sensors
        extra_entities = []
        for room in self.rooms:
            if room.temp_sensor:
                extra_entities.append(room.temp_sensor)
            extra_entities.extend(room.window_sensors)

        if extra_entities:
            self._remove_listeners.append(
                async_track_state_change_event(
                    self.hass,
                    extra_entities,
                    self._async_room_sensor_changed,
                )
            )
            _LOGGER.info(
                "%s: Tracking %d external sensors/window sensors for zone evaluation",
                self.zone_name,
                len(extra_entities),
            )

        # Update zone climate state
        await self._async_update_zone_climate_state()

        # Do initial evaluation
        await self._async_evaluate_zone()

        # Start periodic safety check timer
        self._schedule_periodic_check()
        _LOGGER.info(
            "%s: Periodic safety check enabled (every %d seconds)",
            self.zone_name,
            self._periodic_interval,
        )

    async def async_stop(self) -> None:
        """Stop the zone state machine."""
        await self._async_save_state()

        if self._retry_timer:
            self._retry_timer.cancel()
            self._retry_timer = None

        if self._periodic_timer:
            self._periodic_timer.cancel()
            self._periodic_timer = None

        if self._eval_debounce_timer:
            self._eval_debounce_timer.cancel()
            self._eval_debounce_timer = None

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
        """Handle room state changes - debounced zone evaluation."""
        if self._eval_debounce_timer:
            self._eval_debounce_timer.cancel()

        self._eval_debounce_timer = self.hass.loop.call_later(
            1.0,
            lambda: self.hass.async_create_task(self._async_debounced_evaluate()),
        )

    @callback
    def _on_room_needs_heat_changed(self) -> None:
        """Handle room needs_heat change (e.g. window confirmed open/closed)."""
        if self._eval_debounce_timer:
            self._eval_debounce_timer.cancel()

        self._eval_debounce_timer = self.hass.loop.call_later(
            0.5,
            lambda: self.hass.async_create_task(self._async_debounced_evaluate()),
        )

    @callback
    def _async_room_sensor_changed(self, event: Event) -> None:
        """Handle external sensor/window changes that affect room needs_heat."""
        if self._eval_debounce_timer:
            self._eval_debounce_timer.cancel()

        self._eval_debounce_timer = self.hass.loop.call_later(
            2.0,
            lambda: self.hass.async_create_task(
                self._async_debounced_evaluate()
            ),
        )

    def _schedule_periodic_check(self) -> None:
        """Schedule the next periodic safety check."""
        if self._periodic_timer:
            self._periodic_timer.cancel()

        self._periodic_timer = self.hass.loop.call_later(
            self._periodic_interval,
            lambda: self.hass.async_create_task(self._async_periodic_check()),
        )

    async def _async_periodic_check(self) -> None:
        """Perform periodic safety check to ensure state consistency."""
        try:
            _LOGGER.debug(
                "%s: Running periodic safety check",
                self.zone_name,
            )

            for room in self.rooms:
                try:
                    await room.async_update_climate_state()
                except Exception:
                    _LOGGER.exception(
                        "%s: Error updating room %s during periodic check",
                        self.zone_name,
                        room.room_name,
                    )

            await self._async_evaluate_zone()
        except Exception:
            _LOGGER.exception(
                "%s: Error during periodic safety check",
                self.zone_name,
            )
        finally:
            self._schedule_periodic_check()

    async def _async_update_zone_climate_state(self) -> None:
        """Update zone climate state from entity."""
        state = self.hass.states.get(self.zone_climate)
        if not state:
            return

        old_zone_is_on = self._zone_is_on
        self._zone_current_temp = state.attributes.get("current_temperature")
        self._zone_is_on = state.state == HVACMode.HEAT

        if old_zone_is_on != self._zone_is_on and not self._updating_zone:
            _LOGGER.info(
                "%s: External zone state change detected (%s -> %s), triggering evaluation",
                self.zone_name,
                "ON" if old_zone_is_on else "OFF",
                "ON" if self._zone_is_on else "OFF",
            )
            self._last_zone_change = dt_util.now()
            self.hass.async_create_task(self._async_debounced_evaluate())

    async def _async_debounced_evaluate(self) -> None:
        """Safe wrapper for debounced zone evaluation."""
        try:
            await self._async_evaluate_zone()
        except Exception:
            _LOGGER.exception(
                "%s: Error during zone evaluation (will retry on next trigger)",
                self.zone_name,
            )

    async def _async_evaluate_zone(self) -> None:
        """Evaluate zone state based on room states (with concurrency guard)."""
        async with self._eval_lock:
            await self._async_run_evaluation()

    async def _async_run_evaluation(self) -> None:
        """Perform the actual zone evaluation."""
        if self._retry_timer:
            self._retry_timer.cancel()
            self._retry_timer = None

        _LOGGER.debug("%s: ZONE EVALUATION STARTED", self.zone_name)

        rooms_needing_heat = []
        for room in self.rooms:
            if room.needs_heat and room.temperature_deficit > 0:
                rooms_needing_heat.append(room)
                _LOGGER.debug(
                    "%s:   > %s NEEDS HEAT (deficit: %.1f C)",
                    self.zone_name,
                    room.room_name,
                    room.temperature_deficit,
                )

        rooms_needing_heat.sort(key=lambda r: r.temperature_deficit, reverse=True)

        _LOGGER.debug(
            "%s: %d/%d rooms need heat, zone %s, desired %s",
            self.zone_name,
            len(rooms_needing_heat),
            len(self.rooms),
            "ON" if self._zone_is_on else "OFF",
            "ON" if rooms_needing_heat else "OFF",
        )

        desired_zone_on = len(rooms_needing_heat) > 0

        if self._should_respect_min_cycle_time(desired_zone_on):
            return

        await self._async_update_zone_climate(desired_zone_on, rooms_needing_heat)

    @property
    def zone_is_on(self) -> bool:
        """Return True if zone thermostat is on."""
        return self._zone_is_on

    @property
    def zone_current_temp(self) -> float | None:
        """Return zone thermostat current temperature."""
        return self._zone_current_temp

    @property
    def last_zone_change(self):
        """Return time of last zone state change."""
        return self._last_zone_change

    @property
    def retry_timer_active(self) -> bool:
        """Return True if retry timer is active."""
        return self._retry_timer is not None

    @property
    def in_startup_grace_period(self) -> bool:
        """Return True if in startup grace period."""
        return self._is_in_startup_grace_period()

    def _is_in_startup_grace_period(self) -> bool:
        """Check if we're still in the startup grace period."""
        if self._startup_time is None:
            return False

        time_since_startup = (dt_util.now() - self._startup_time).total_seconds()
        return time_since_startup < STARTUP_GRACE_PERIOD

    def _should_respect_min_cycle_time(self, desired_on: bool) -> bool:
        """Check if we should respect minimum cycle time."""
        if self._is_in_startup_grace_period():
            time_since_startup = (dt_util.now() - self._startup_time).total_seconds()
            _LOGGER.debug(
                "%s: In startup grace period (%.0fs elapsed of %ds), bypassing min_cycle_time",
                self.zone_name,
                time_since_startup,
                STARTUP_GRACE_PERIOD,
            )
            return False

        if self._last_zone_change is None:
            _LOGGER.debug("%s: No previous change, allowing action", self.zone_name)
            return False

        if desired_on == self._zone_is_on:
            _LOGGER.debug(
                "%s: Zone already in desired state (%s), no change needed",
                self.zone_name,
                "ON" if self._zone_is_on else "OFF",
            )
            return False

        time_since_change = (
            dt_util.now() - self._last_zone_change
        ).total_seconds() / 60

        if time_since_change < self.min_cycle_time:
            time_remaining = self.min_cycle_time - time_since_change
            time_remaining_seconds = time_remaining * 60

            _LOGGER.warning(
                "%s: MIN CYCLE TIME BLOCKING CHANGE! "
                "Would turn zone %s but only %.1f min elapsed (min: %d min, %.1f min remaining)",
                self.zone_name,
                "OFF->ON" if desired_on else "ON->OFF",
                time_since_change,
                self.min_cycle_time,
                time_remaining,
            )

            _LOGGER.info(
                "%s: Scheduling automatic retry in %.1f minutes",
                self.zone_name,
                time_remaining,
            )
            self._retry_timer = self.hass.loop.call_later(
                time_remaining_seconds,
                lambda: self.hass.async_create_task(self._async_debounced_evaluate()),
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
        zone_state = self.hass.states.get(self.zone_climate)
        if not zone_state:
            _LOGGER.warning(
                "%s: Zone climate %s not found", self.zone_name, self.zone_climate
            )
            return

        zone_temp = zone_state.attributes.get("current_temperature")
        zone_hvac = zone_state.state

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

        _LOGGER.info(
            "%s: CHANGING ZONE CLIMATE %s -> %s",
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
                    "%s:   -> %s (deficit: %.1f C)",
                    self.zone_name,
                    room.room_name,
                    room.temperature_deficit,
                )
        else:
            _LOGGER.info("%s:   No rooms need heat", self.zone_name)

        self._updating_zone = True

        try:
            if turn_on:
                target_temp = (zone_temp + 5) if zone_temp is not None else 25
                _LOGGER.info(
                    "%s: Setting zone temperature: %.1f C -> %.1f C (current + 5 C)",
                    self.zone_name,
                    zone_temp or 0,
                    target_temp,
                )

                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_SET_TEMPERATURE,
                    {
                        ATTR_ENTITY_ID: self.zone_climate,
                        ATTR_TEMPERATURE: target_temp,
                    },
                    blocking=True,
                )
            else:
                _LOGGER.info(
                    "%s: Turning OFF - no temperature change needed", self.zone_name
                )

            _LOGGER.info(
                "%s: Setting HVAC mode to %s",
                self.zone_name,
                HVACMode.HEAT if turn_on else HVACMode.OFF,
            )
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_HVAC_MODE,
                {
                    ATTR_ENTITY_ID: self.zone_climate,
                    "hvac_mode": HVACMode.HEAT if turn_on else HVACMode.OFF,
                },
                blocking=True,
            )

            self._zone_is_on = turn_on
            self._last_zone_change = dt_util.now()
        except Exception:
            _LOGGER.exception(
                "%s: Failed to change zone climate to %s - will retry on next evaluation",
                self.zone_name,
                "ON" if turn_on else "OFF",
            )
            return
        finally:
            self._updating_zone = False

        _LOGGER.info(
            "%s: Zone change complete - now %s (min_cycle_time reset)",
            self.zone_name,
            "ON" if turn_on else "OFF",
        )

    async def _async_restore_state(self) -> bool:
        """Restore state from persistent storage. Returns True if state was restored."""
        if self._storage is None:
            return False

        stored = self._storage.get_zone_state(self.zone_name)
        if stored is None:
            return False

        saved_at = parse_datetime(stored.get("saved_at"))
        if saved_at is None:
            return False

        age_hours = (dt_util.now() - saved_at).total_seconds() / 3600
        if age_hours > 24:
            _LOGGER.info(
                "%s: Stored state too old (%.1f hours), starting fresh",
                self.zone_name,
                age_hours,
            )
            self._storage.clear_zone_state(self.zone_name)
            return False

        self._zone_is_on = stored.get("zone_is_on", False)
        self._last_zone_change = parse_datetime(stored.get("last_zone_change"))

        _LOGGER.info(
            "%s: Restored state - zone_is_on=%s, last_change=%s",
            self.zone_name,
            self._zone_is_on,
            self._last_zone_change,
        )

        return self._last_zone_change is not None

    async def _async_save_state(self) -> None:
        """Save current state to persistent storage."""
        if self._storage is None:
            return

        self._storage.set_zone_state(
            zone_name=self.zone_name,
            zone_is_on=self._zone_is_on,
            last_zone_change=self._last_zone_change,
        )

        _LOGGER.debug(
            "%s: Saved state - zone_is_on=%s, last_change=%s",
            self.zone_name,
            self._zone_is_on,
            self._last_zone_change,
        )
