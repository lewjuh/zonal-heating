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
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_HOME
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
        person_entities: list[str] | None = None,
        away_temperature: float = 16.0,
        away_mode_delay: int = 10,
        storage: ZonalHeatingStorage | None = None,
    ) -> None:
        """Initialize zone state machine."""
        self.hass = hass
        self.zone_name = zone_name
        self.zone_climate = zone_climate
        self.rooms = rooms
        self.min_cycle_time = min_cycle_time
        self.person_entities = person_entities or []
        self.away_temperature = away_temperature
        self.away_mode_delay = away_mode_delay
        self._storage = storage

        # State tracking
        self._zone_is_on = False
        self._last_zone_change = None
        self._zone_current_temp: float | None = None
        self._away_mode = False
        self._away_mode_pending = False
        self._people_home_count = 0

        # Pre-away target temperatures for restore on return
        self._pre_away_targets: dict[str, float] = {}

        # Startup tracking - ignore min_cycle_time during grace period
        self._startup_time = None

        # Retry timer for min_cycle_time blocking
        self._retry_timer: asyncio.TimerHandle | None = None

        # Away mode delay timer
        self._away_mode_timer: asyncio.TimerHandle | None = None
        self._away_mode_timer_started = None

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

        # Record startup time for grace period
        self._startup_time = dt_util.now()

        # Restore previous state if available
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

        # Track person entities if configured
        if self.person_entities:
            self._remove_listeners.append(
                async_track_state_change_event(
                    self.hass,
                    self.person_entities,
                    self._async_person_changed,
                )
            )
            _LOGGER.info(
                "%s: Tracking %d person entities for away mode",
                self.zone_name,
                len(self.person_entities),
            )

        # Update zone climate state
        await self._async_update_zone_climate_state()

        # Update person states
        self._update_person_states()

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
        # Save state before stopping
        await self._async_save_state()

        # Cancel any pending retry timer
        if self._retry_timer:
            self._retry_timer.cancel()
            self._retry_timer = None

        # Cancel any pending away mode timer
        if self._away_mode_timer:
            self._away_mode_timer.cancel()
            self._away_mode_timer = None

        # Cancel periodic safety check timer
        if self._periodic_timer:
            self._periodic_timer.cancel()
            self._periodic_timer = None

        # Cancel debounce timer
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
            lambda: self.hass.async_create_task(self._async_evaluate_zone()),
        )

    @callback
    def _async_person_changed(self, event: Event) -> None:
        """Handle person state changes."""
        new_state = event.data.get("new_state")

        if new_state:
            old_away_mode = self._away_mode
            self._update_person_states()

            if old_away_mode != self._away_mode:
                if self._away_mode:
                    self._start_away_mode_delay_timer()
                else:
                    if self._away_mode_timer:
                        self._away_mode_timer.cancel()
                        self._away_mode_timer = None
                        self._away_mode_pending = False
                        _LOGGER.info(
                            "%s: Away mode cancelled - someone returned home (People home: %d/%d)",
                            self.zone_name,
                            self._people_home_count,
                            len(self.person_entities),
                        )
                    else:
                        _LOGGER.info(
                            "%s: Away mode ended - people returned home (People home: %d/%d)",
                            self.zone_name,
                            self._people_home_count,
                            len(self.person_entities),
                        )
                    # Restore pre-away temperatures and evaluate
                    self.hass.async_create_task(self._async_restore_from_away_mode())

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
        _LOGGER.debug(
            "%s: Running periodic safety check",
            self.zone_name,
        )

        # Re-read all room states to ensure they're current
        for room in self.rooms:
            await room._async_update_climate_state()

        # Evaluate zone state
        await self._async_evaluate_zone()

        # Schedule next check
        self._schedule_periodic_check()

    async def _async_update_zone_climate_state(self) -> None:
        """Update zone climate state from entity."""
        state = self.hass.states.get(self.zone_climate)
        if not state:
            return

        old_zone_is_on = self._zone_is_on
        self._zone_current_temp = state.attributes.get("current_temperature")
        self._zone_is_on = state.state == HVACMode.HEAT

        # Detect external changes (manual override) and trigger evaluation
        if old_zone_is_on != self._zone_is_on and not self._updating_zone:
            _LOGGER.info(
                "%s: External zone state change detected (%s -> %s), triggering evaluation",
                self.zone_name,
                "ON" if old_zone_is_on else "OFF",
                "ON" if self._zone_is_on else "OFF",
            )
            self._last_zone_change = dt_util.now()
            self.hass.async_create_task(self._async_evaluate_zone())

    def _update_person_states(self) -> None:
        """Update person states and away mode."""
        if not self.person_entities:
            self._away_mode = False
            self._people_home_count = 0
            return

        people_home = sum(
            1
            for person_entity in self.person_entities
            if self.hass.states.is_state(person_entity, STATE_HOME)
        )

        self._people_home_count = people_home
        self._away_mode = people_home == 0

    @property
    def away_mode(self) -> bool:
        """Return True if in away mode (all people away)."""
        return self._away_mode

    @property
    def people_home_count(self) -> int:
        """Return number of people currently home."""
        return self._people_home_count

    def _start_away_mode_delay_timer(self, delay_seconds: float | None = None) -> None:
        """Start delay timer before activating away mode."""
        if self._away_mode_timer:
            self._away_mode_timer.cancel()

        self._away_mode_pending = True
        self._away_mode_timer_started = dt_util.now()

        if delay_seconds is None:
            delay_seconds = self.away_mode_delay * 60

        _LOGGER.info(
            "%s: Everyone left - will activate away mode in %.1f minutes",
            self.zone_name,
            delay_seconds / 60,
        )

        self._away_mode_timer = self.hass.loop.call_later(
            delay_seconds,
            lambda: self.hass.async_create_task(self._async_away_mode_delay_expired()),
        )

    async def _async_away_mode_delay_expired(self) -> None:
        """Handle away mode delay expiration - confirm still away and activate."""
        self._away_mode_timer = None
        self._away_mode_pending = False

        if not self._away_mode:
            _LOGGER.info(
                "%s: Away mode delay expired but people are home, ignoring",
                self.zone_name,
            )
            return

        _LOGGER.info(
            "%s: Away mode delay expired - activating away mode after %d minute delay",
            self.zone_name,
            self.away_mode_delay,
        )

        await self._async_evaluate_zone()

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

        # Check if away mode is pending (timer running)
        if self._away_mode_pending:
            _LOGGER.debug(
                "%s: Away mode pending - waiting %d min delay (timer active)",
                self.zone_name,
                self.away_mode_delay,
            )
            if self._zone_is_on:
                zone_state = self.hass.states.get(self.zone_climate)
                if zone_state and zone_state.state == HVACMode.HEAT:
                    _LOGGER.info(
                        "%s: Turning zone OFF while waiting for away mode activation",
                        self.zone_name,
                    )
                    await self.hass.services.async_call(
                        CLIMATE_DOMAIN,
                        SERVICE_SET_HVAC_MODE,
                        {
                            ATTR_ENTITY_ID: self.zone_climate,
                            "hvac_mode": HVACMode.OFF,
                        },
                        blocking=True,
                    )
                    self._zone_is_on = False
            return

        # Check if away mode is confirmed active (after delay)
        if self._away_mode and self.person_entities and not self._away_mode_timer:
            _LOGGER.info(
                "%s: AWAY MODE ACTIVE - All people away, entering low power mode",
                self.zone_name,
            )
            await self._async_handle_away_mode()
            return

        # Build rooms needing heat and log in a single pass
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

    async def _async_handle_away_mode(self) -> None:
        """Handle away mode - save targets, set all TRVs to away temperature, turn off zone."""
        _LOGGER.info(
            "%s: AWAY MODE - Setting all TRVs to %.1f C and turning zone OFF",
            self.zone_name,
            self.away_temperature,
        )

        # Save current TRV target temperatures before overwriting
        self._pre_away_targets.clear()
        for room in self.rooms:
            if room.target_temperature is not None:
                self._pre_away_targets[room.room_name] = room.target_temperature
                _LOGGER.debug(
                    "%s: Saved pre-away target for %s: %.1f C",
                    self.zone_name,
                    room.room_name,
                    room.target_temperature,
                )

        # Set all room TRVs to away temperature
        for room in self.rooms:
            _LOGGER.info(
                "%s:   -> Setting %s to away temperature (%.1f C)",
                self.zone_name,
                room.room_name,
                self.away_temperature,
            )

            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                {
                    ATTR_ENTITY_ID: room.climate_entity,
                    ATTR_TEMPERATURE: self.away_temperature,
                },
                blocking=False,
            )

        # Turn off zone thermostat
        zone_state = self.hass.states.get(self.zone_climate)
        if zone_state and zone_state.state == HVACMode.HEAT:
            _LOGGER.info(
                "%s: Turning zone thermostat OFF for away mode",
                self.zone_name,
            )
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_HVAC_MODE,
                {
                    ATTR_ENTITY_ID: self.zone_climate,
                    "hvac_mode": HVACMode.OFF,
                },
                blocking=True,
            )
            self._zone_is_on = False

        _LOGGER.info(
            "%s: Away mode complete - all TRVs at %.1f C, zone OFF",
            self.zone_name,
            self.away_temperature,
        )

    async def _async_restore_from_away_mode(self) -> None:
        """Restore TRV target temperatures after people return home."""
        if self._pre_away_targets:
            _LOGGER.info(
                "%s: Restoring pre-away temperatures for %d room(s)",
                self.zone_name,
                len(self._pre_away_targets),
            )
            for room in self.rooms:
                saved_target = self._pre_away_targets.get(room.room_name)
                if saved_target is not None:
                    _LOGGER.info(
                        "%s:   -> Restoring %s to %.1f C",
                        self.zone_name,
                        room.room_name,
                        saved_target,
                    )
                    await self.hass.services.async_call(
                        CLIMATE_DOMAIN,
                        SERVICE_SET_TEMPERATURE,
                        {
                            ATTR_ENTITY_ID: room.climate_entity,
                            ATTR_TEMPERATURE: saved_target,
                        },
                        blocking=False,
                    )
            self._pre_away_targets.clear()

        await self._async_evaluate_zone()

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

        if stored.get("away_mode_pending") and stored.get("away_mode_timer_remaining"):
            remaining = stored["away_mode_timer_remaining"]
            if remaining > 0:
                _LOGGER.info(
                    "%s: Restoring away mode timer with %.1f seconds remaining",
                    self.zone_name,
                    remaining,
                )
                self._start_away_mode_delay_timer(delay_seconds=remaining)

        return self._last_zone_change is not None

    async def _async_save_state(self) -> None:
        """Save current state to persistent storage."""
        if self._storage is None:
            return

        away_timer_remaining = None
        if self._away_mode_pending and self._away_mode_timer_started:
            elapsed = (dt_util.now() - self._away_mode_timer_started).total_seconds()
            total_delay = self.away_mode_delay * 60
            away_timer_remaining = max(0, total_delay - elapsed)

        self._storage.set_zone_state(
            zone_name=self.zone_name,
            zone_is_on=self._zone_is_on,
            last_zone_change=self._last_zone_change,
            away_mode_pending=self._away_mode_pending,
            away_mode_timer_remaining=away_timer_remaining,
        )

        _LOGGER.debug(
            "%s: Saved state - zone_is_on=%s, last_change=%s, away_pending=%s",
            self.zone_name,
            self._zone_is_on,
            self._last_zone_change,
            self._away_mode_pending,
        )
