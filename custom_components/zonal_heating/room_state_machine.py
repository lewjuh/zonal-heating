"""Room state machine for zonal heating integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_TURN_OFF,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)


class RoomStateMachine:
    """State machine for managing a single room's heating logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        room_name: str,
        climate_entity: str,
        window_sensors: list[str],
        window_delay: int = 30,
        temp_differential: float = 0.5,
        overheat_threshold: float = 1.0,
        temp_sensor: str | None = None,
    ) -> None:
        """Initialize room state machine."""
        self.hass = hass
        self.room_name = room_name
        self.climate_entity = climate_entity
        self.window_sensors = window_sensors
        self.window_delay = window_delay
        self.temp_differential = temp_differential
        self.overheat_threshold = overheat_threshold
        self.temp_sensor = temp_sensor

        # State tracking
        self._window_open = False
        self._window_open_confirmed = False  # True after delay expires
        self._window_timer: asyncio.TimerHandle | None = None
        self._current_temp: float | None = None
        self._target_temp: float | None = None
        self._is_on = False
        self._overheated = False

        # Listeners
        self._remove_listeners: list[Callable] = []

    async def async_start(self) -> None:
        """Start the room state machine."""
        _LOGGER.debug("Starting room state machine for %s", self.room_name)

        # Track climate entity changes
        self._remove_listeners.append(
            async_track_state_change_event(
                self.hass,
                [self.climate_entity],
                self._async_climate_changed,
            )
        )

        # Track window sensors
        if self.window_sensors:
            self._remove_listeners.append(
                async_track_state_change_event(
                    self.hass,
                    self.window_sensors,
                    self._async_window_changed,
                )
            )

        # Track external temperature sensor
        if self.temp_sensor:
            self._remove_listeners.append(
                async_track_state_change_event(
                    self.hass,
                    [self.temp_sensor],
                    self._async_temp_sensor_changed,
                )
            )
            _LOGGER.info(
                "%s: Using external temperature sensor %s",
                self.room_name,
                self.temp_sensor,
            )

        # Initialize state
        await self._async_update_climate_state()
        self._update_window_state()

    async def async_stop(self) -> None:
        """Stop the room state machine."""
        for remove_listener in self._remove_listeners:
            remove_listener()
        self._remove_listeners.clear()

        if self._window_timer:
            self._window_timer.cancel()
            self._window_timer = None

    @callback
    def _async_climate_changed(self, event: Event) -> None:
        """Handle climate entity state changes."""
        self.hass.async_create_task(self._async_update_climate_state())

    @callback
    def _async_temp_sensor_changed(self, event: Event) -> None:
        """Handle external temperature sensor state changes."""
        self.hass.async_create_task(self._async_update_climate_state())

    @callback
    def _async_window_changed(self, event: Event) -> None:
        """Handle window sensor state changes."""
        old_state = self._window_open
        self._update_window_state()
        new_state = self._window_open

        if old_state != new_state:
            if new_state:
                # Window opened - start delay timer
                self._start_window_delay_timer()
            else:
                # Window closed - cancel timer and clear confirmed flag
                if self._window_timer:
                    self._window_timer.cancel()
                    self._window_timer = None
                self._window_open_confirmed = False
                _LOGGER.info("%s: Window closed", self.room_name)

    def _update_window_state(self) -> None:
        """Update window open state from sensors."""
        self._window_open = any(
            self.hass.states.is_state(sensor, STATE_ON)
            for sensor in self.window_sensors
        )

    def _start_window_delay_timer(self) -> None:
        """Start delay timer before confirming window open and turning off TRV."""
        if self._window_timer:
            self._window_timer.cancel()

        _LOGGER.info(
            "%s: Window opened, will confirm and turn off TRV in %d seconds",
            self.room_name,
            self.window_delay,
        )

        self._window_timer = self.hass.loop.call_later(
            self.window_delay,
            lambda: self.hass.async_create_task(self._async_window_delay_expired()),
        )

    async def _async_window_delay_expired(self) -> None:
        """Handle window delay expiration - confirm window open and turn off TRV."""
        self._window_timer = None

        # Confirm window is still open
        if not self._window_open:
            _LOGGER.info(
                "%s: Window delay expired but window already closed, ignoring",
                self.room_name,
            )
            return

        # Mark window as confirmed after delay
        self._window_open_confirmed = True
        _LOGGER.info(
            "%s: Window open confirmed after %d second delay, turning off TRV",
            self.room_name,
            self.window_delay,
        )

        # Turn off TRV
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self.climate_entity},
            blocking=True,
        )

    async def _async_update_climate_state(self) -> None:
        """Update climate state from entity."""
        state = self.hass.states.get(self.climate_entity)
        if not state:
            return

        old_current = self._current_temp
        old_target = self._target_temp
        old_is_on = self._is_on
        old_overheated = self._overheated

        # Calculate old heating need before updating
        old_needs_heat = self.needs_heat

        # Use external temperature sensor if configured, otherwise use climate entity
        if self.temp_sensor:
            temp_state = self.hass.states.get(self.temp_sensor)
            if temp_state and temp_state.state not in ("unavailable", "unknown"):
                try:
                    self._current_temp = float(temp_state.state)
                except (ValueError, TypeError):
                    self._current_temp = state.attributes.get("current_temperature")
            else:
                self._current_temp = state.attributes.get("current_temperature")
        else:
            self._current_temp = state.attributes.get("current_temperature")
        self._target_temp = state.attributes.get("temperature")
        self._is_on = state.state not in ("off", "unavailable", "unknown")

        # Calculate new heating need after updating
        new_needs_heat = self.needs_heat

        # Log significant changes
        if old_current != self._current_temp or old_target != self._target_temp:
            _LOGGER.debug(
                "%s: Temp update - Current: %.1f°C, Target: %.1f°C, Deficit: %.1f°C",
                self.room_name,
                self._current_temp or 0,
                self._target_temp or 0,
                self.temperature_deficit,
            )

        # Log target temperature changes specifically
        if old_target != self._target_temp:
            _LOGGER.info(
                "%s: Target temperature changed: %.1f°C → %.1f°C",
                self.room_name,
                old_target or 0,
                self._target_temp or 0,
            )

        if old_is_on != self._is_on:
            _LOGGER.info(
                "%s: Climate turned %s",
                self.room_name,
                "ON" if self._is_on else "OFF",
            )

        # Log if heating need status changed
        if old_needs_heat != new_needs_heat:
            _LOGGER.info(
                "%s: Heating need changed: %s → %s",
                self.room_name,
                "NEEDS HEAT" if old_needs_heat else "NO HEAT",
                "NEEDS HEAT" if new_needs_heat else "NO HEAT",
            )

        # Check for overheating and turn off TRV if needed
        await self._async_check_overheat(old_overheated)

    @property
    def needs_heat(self) -> bool:
        """Return True if room needs heat."""
        # If overheated, definitely don't need more heat
        if self._overheated:
            _LOGGER.debug("%s: No heat needed - room is overheated", self.room_name)
            return False

        if not self._is_on:
            _LOGGER.debug("%s: No heat needed - climate is OFF", self.room_name)
            return False

        if self._window_open_confirmed:
            _LOGGER.debug(
                "%s: No heat needed - window is confirmed open", self.room_name
            )
            return False

        if self._current_temp is None or self._target_temp is None:
            _LOGGER.debug(
                "%s: No heat needed - missing temperature data", self.room_name
            )
            return False

        # Room needs heat if current temp is below (target - differential)
        threshold = self._target_temp - self.temp_differential
        needs_heat = self._current_temp < threshold

        if needs_heat:
            _LOGGER.debug(
                "%s: NEEDS HEAT - Current: %.1f°C < Threshold: %.1f°C (Target: %.1f°C - Diff: %.1f°C)",
                self.room_name,
                self._current_temp,
                threshold,
                self._target_temp,
                self.temp_differential,
            )
        else:
            _LOGGER.debug(
                "%s: No heat needed - Current: %.1f°C >= Threshold: %.1f°C",
                self.room_name,
                self._current_temp,
                threshold,
            )

        return needs_heat

    @property
    def temperature_deficit(self) -> float:
        """Return temperature deficit (target - current)."""
        if self._current_temp is None or self._target_temp is None:
            return 0.0

        return self._target_temp - self._current_temp

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        return self._current_temp

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return self._target_temp

    @property
    def window_open(self) -> bool:
        """Return True if window is open."""
        return self._window_open

    @property
    def is_on(self) -> bool:
        """Return True if climate is on."""
        return self._is_on

    @property
    def overheated(self) -> bool:
        """Return True if room is overheated."""
        return self._overheated

    async def _async_check_overheat(self, was_overheated: bool) -> None:
        """Check if room is overheating and turn off TRV if needed."""
        if self._current_temp is None or self._target_temp is None:
            self._overheated = False
            return

        overheat_limit = self._target_temp + self.overheat_threshold
        is_overheating = self._current_temp >= overheat_limit

        if is_overheating:
            if not was_overheated:
                self._overheated = True
                _LOGGER.info(
                    "%s: OVERHEAT - Current: %.1f°C >= Limit: %.1f°C (Target: %.1f°C + %.1f°C), turning off TRV",
                    self.room_name,
                    self._current_temp,
                    overheat_limit,
                    self._target_temp,
                    self.overheat_threshold,
                )

                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: self.climate_entity},
                    blocking=True,
                )
        elif was_overheated:
            # Temperature dropped below overheat limit - turn TRV back on
            self._overheated = False
            _LOGGER.info(
                "%s: OVERHEAT CLEARED - Temp %.1f°C < Limit %.1f°C, turning TRV back on",
                self.room_name,
                self._current_temp,
                overheat_limit,
            )

            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_HVAC_MODE,
                {
                    ATTR_ENTITY_ID: self.climate_entity,
                    "hvac_mode": HVACMode.HEAT,
                },
                blocking=True,
            )
