"""Room state machine for zonal heating integration."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_ON
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from .storage import ZonalHeatingStorage

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
        temp_sensor: str | None = None,
        calibration_sync: bool = False,
        storage: "ZonalHeatingStorage | None" = None,
    ) -> None:
        """Initialize room state machine."""
        self.hass = hass
        self.room_name = room_name
        self.climate_entity = climate_entity
        self.window_sensors = window_sensors
        self.window_delay = window_delay
        self.temp_differential = temp_differential
        self.temp_sensor = temp_sensor
        self.calibration_sync = calibration_sync
        self._storage = storage

        # State tracking
        self._window_open = False
        self._window_open_confirmed = False
        self._window_timer: asyncio.TimerHandle | None = None
        self._window_timer_started: datetime | None = None
        self._current_temp: float | None = None
        self._target_temp: float | None = None
        self._is_on = False

        # Calibration sync tracking
        self._calibration_entity: str | None = None
        self._last_calibration: float | None = None
        self._calibration_available = False

        # External temperature sync tracking (some TRVs accept direct temp input)
        self._external_temp_entity: str | None = None
        self._last_external_temp_sync: float | None = None
        self._external_temp_available = False

        # Temperature sensor selector (some TRVs need this set to "external")
        self._temp_sensor_selector: str | None = None

        # Direct MQTT sync for Zigbee2MQTT devices without exposed entities
        self._mqtt_friendly_name: str | None = None
        self._mqtt_calibration_available = False
        self._mqtt_control_available = False

        # Callback to notify zone when needs_heat changes
        self._on_needs_heat_changed: Callable[[], None] | None = None

        # Listeners
        self._remove_listeners: list[Callable] = []

    async def async_start(self) -> None:
        """Start the room state machine."""
        _LOGGER.debug("Starting room state machine for %s", self.room_name)

        # Restore previous state if available
        await self._async_restore_state()

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

        # Discover calibration/external temp entity if calibration sync is enabled
        if self.calibration_sync and self.temp_sensor:
            _LOGGER.info(
                "%s: Calibration sync enabled, discovering sync entities for TRV %s",
                self.room_name,
                self.climate_entity,
            )
            await self._async_discover_sync_entities()
            if self._external_temp_available or self._calibration_available or self._mqtt_calibration_available:
                self.hass.loop.call_later(
                    5.0,
                    lambda: self.hass.async_create_task(self._async_forced_initial_sync()),
                )
        else:
            # MQTT discovery for direct device control (bypasses HA quirks)
            await self._async_try_mqtt_discovery()
            if self.calibration_sync and not self.temp_sensor:
                _LOGGER.info(
                    "%s: Calibration sync enabled but no external temp sensor configured - skipping",
                    self.room_name,
                )

        # Initialize state
        await self.async_update_climate_state()
        self._update_window_state()

        # Start window timer if window is open and not already confirmed
        if self._window_open and not self._window_open_confirmed:
            _LOGGER.info(
                "%s: Window open on startup, starting %ds confirmation timer",
                self.room_name,
                self.window_delay,
            )
            self._start_window_delay_timer()

    async def async_stop(self) -> None:
        """Stop the room state machine."""
        await self._async_save_state()

        for remove_listener in self._remove_listeners:
            remove_listener()
        self._remove_listeners.clear()

        if self._window_timer:
            self._window_timer.cancel()
            self._window_timer = None

    @callback
    def _async_climate_changed(self, event: Event) -> None:
        """Handle climate entity state changes."""
        self.hass.async_create_task(self.async_update_climate_state())

    @callback
    def _async_temp_sensor_changed(self, event: Event) -> None:
        """Handle external temperature sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state:
            _LOGGER.debug(
                "%s: External sensor changed to %.1f°C (sync will be triggered)",
                self.room_name,
                float(new_state.state) if new_state.state not in ("unavailable", "unknown") else 0,
            )
        self.hass.async_create_task(
            self.async_update_climate_state(sync_calibration=True)
        )

    @callback
    def _async_window_changed(self, event: Event) -> None:
        """Handle window sensor state changes."""
        old_state = self._window_open
        self._update_window_state()
        new_state = self._window_open

        if old_state != new_state:
            if new_state:
                self._start_window_delay_timer()
            else:
                if self._window_timer:
                    self._window_timer.cancel()
                    self._window_timer = None

                was_confirmed = self._window_open_confirmed
                self._window_open_confirmed = False

                if was_confirmed:
                    _LOGGER.info(
                        "%s: Window closed, resuming heat requests",
                        self.room_name,
                    )
                    self._notify_needs_heat_changed()
                else:
                    _LOGGER.info("%s: Window closed", self.room_name)

    def _update_window_state(self) -> None:
        """Update window open state from sensors."""
        self._window_open = any(
            self.hass.states.is_state(sensor, STATE_ON)
            for sensor in self.window_sensors
        )

    def _start_window_delay_timer(self, delay_seconds: float | None = None) -> None:
        """Start delay timer before confirming window open."""
        if self._window_timer:
            self._window_timer.cancel()

        self._window_timer_started = dt_util.now()

        if delay_seconds is None:
            delay_seconds = self.window_delay

        _LOGGER.info(
            "%s: Window opened, will confirm in %.0f seconds",
            self.room_name,
            delay_seconds,
        )

        self._window_timer = self.hass.loop.call_later(
            delay_seconds,
            lambda: self.hass.async_create_task(self._async_window_delay_expired()),
        )

    async def _async_window_delay_expired(self) -> None:
        """Handle window delay expiration - confirm window open."""
        self._window_timer = None

        if not self._window_open:
            _LOGGER.info(
                "%s: Window delay expired but window already closed, ignoring",
                self.room_name,
            )
            return

        self._window_open_confirmed = True
        _LOGGER.info(
            "%s: Window open confirmed after %d second delay - suppressing heat requests",
            self.room_name,
            self.window_delay,
        )
        self._notify_needs_heat_changed()

    async def _async_discover_sync_entities(self) -> None:
        """Discover calibration or external temp entities for this TRV."""
        device_name = self.climate_entity.split(".")[-1]

        entity_reg = er.async_get(self.hass)
        climate_entry = entity_reg.async_get(self.climate_entity)

        if climate_entry and climate_entry.device_id:
            device_id = climate_entry.device_id
            _LOGGER.debug(
                "%s: Found device_id %s for TRV, searching for related entities",
                self.room_name,
                device_id,
            )

            for entry in er.async_entries_for_device(entity_reg, device_id):
                if entry.domain != NUMBER_DOMAIN:
                    continue

                entity_id = entry.entity_id
                entity_name = entity_id.lower()

                if any(
                    kw in entity_name
                    for kw in ["external", "room_sensor", "measured_room"]
                ):
                    state = self.hass.states.get(entity_id)
                    if state and state.state not in ("unavailable", "unknown"):
                        self._external_temp_entity = entity_id
                        self._external_temp_available = True
                        _LOGGER.info(
                            "%s: Found external temp entity via device registry: %s",
                            self.room_name,
                            entity_id,
                        )
                        await self._async_configure_temp_sensor_selector(device_name)
                        return

                if any(
                    kw in entity_name
                    for kw in ["calibration", "offset", "local_temp"]
                ):
                    state = self.hass.states.get(entity_id)
                    if state and state.state not in ("unavailable", "unknown"):
                        self._calibration_entity = entity_id
                        self._calibration_available = True
                        _LOGGER.info(
                            "%s: Found calibration entity via device registry: %s",
                            self.room_name,
                            entity_id,
                        )
                        return

        # Fallback: try pattern matching with common naming conventions
        external_temp_patterns = [
            f"number.{device_name}_external_measured_room_sensor",
            f"number.{device_name}_external_temperature",
            f"number.{device_name}_external_temp_sensor",
            f"number.{device_name}_room_sensor",
        ]

        for pattern in external_temp_patterns:
            state = self.hass.states.get(pattern)
            if state and state.state not in ("unavailable", "unknown"):
                self._external_temp_entity = pattern
                self._external_temp_available = True
                _LOGGER.info(
                    "%s: Found external temp sync entity: %s (pattern match)",
                    self.room_name,
                    pattern,
                )
                await self._async_configure_temp_sensor_selector(device_name)
                return

        calibration_patterns = [
            f"number.{device_name}_local_temperature_calibration",
            f"number.{device_name}_temperature_offset",
            f"number.{device_name}_local_temp_calibration",
            f"number.{device_name}_calibration",
            f"number.{device_name}_temp_calibration",
        ]

        for pattern in calibration_patterns:
            state = self.hass.states.get(pattern)
            if state and state.state not in ("unavailable", "unknown"):
                self._calibration_entity = pattern
                self._calibration_available = True
                _LOGGER.info(
                    "%s: Found calibration entity: %s (pattern match)",
                    self.room_name,
                    pattern,
                )
                return

        # Fallback: Try direct MQTT for Zigbee2MQTT devices
        await self._async_try_mqtt_discovery()

        if not self._mqtt_calibration_available:
            _LOGGER.warning(
                "%s: Calibration sync enabled but no sync method found. "
                "Searched device registry, patterns, and MQTT. TRV: %s",
                self.room_name,
                self.climate_entity,
            )
        self._calibration_available = False
        self._external_temp_available = False

    async def _async_configure_temp_sensor_selector(self, device_name: str) -> None:
        """Find and configure temperature sensor selector to use external sensor."""
        selector_entity = None

        entity_reg = er.async_get(self.hass)
        climate_entry = entity_reg.async_get(self.climate_entity)

        if climate_entry and climate_entry.device_id:
            device_id = climate_entry.device_id

            for entry in er.async_entries_for_device(entity_reg, device_id):
                if entry.domain != SELECT_DOMAIN:
                    continue

                entity_id = entry.entity_id
                entity_name = entity_id.lower()

                if any(kw in entity_name for kw in ["sensor", "temperature_sensor"]):
                    selector_entity = entity_id
                    _LOGGER.debug(
                        "%s: Found sensor selector via device registry: %s",
                        self.room_name,
                        entity_id,
                    )
                    break

        if not selector_entity:
            selector_patterns = [
                f"select.{device_name}_sensor",
                f"select.{device_name}_temperature_sensor",
                f"select.{device_name}_temp_sensor",
                f"select.{device_name}_sensor_mode",
            ]

            for pattern in selector_patterns:
                state = self.hass.states.get(pattern)
                if state and state.state not in ("unavailable", "unknown"):
                    selector_entity = pattern
                    break

        if not selector_entity:
            _LOGGER.debug(
                "%s: No temperature sensor selector found",
                self.room_name,
            )
            return

        state = self.hass.states.get(selector_entity)
        if not state or state.state in ("unavailable", "unknown"):
            return

        self._temp_sensor_selector = selector_entity
        current_mode = state.state.lower()

        if "external" in current_mode:
            _LOGGER.info(
                "%s: Temperature sensor selector %s already set to: %s",
                self.room_name,
                selector_entity,
                state.state,
            )
            return

        options = state.attributes.get("options", [])
        _LOGGER.debug(
            "%s: Sensor selector options: %s",
            self.room_name,
            options,
        )

        external_option = None
        for option in options:
            if "external" in option.lower():
                external_option = option
                break

        if external_option:
            try:
                await self.hass.services.async_call(
                    SELECT_DOMAIN,
                    "select_option",
                    {
                        ATTR_ENTITY_ID: selector_entity,
                        "option": external_option,
                    },
                    blocking=True,
                )
                _LOGGER.info(
                    "%s: Set temperature sensor selector %s to: %s",
                    self.room_name,
                    selector_entity,
                    external_option,
                )
            except Exception:
                _LOGGER.exception(
                    "%s: Failed to set temperature sensor selector",
                    self.room_name,
                )
        else:
            _LOGGER.warning(
                "%s: Found sensor selector %s but no 'external' option available. Options: %s",
                self.room_name,
                selector_entity,
                options,
            )

    async def _async_forced_initial_sync(self) -> None:
        """Force sync external temperature to TRV on startup, bypassing thresholds."""
        if not self.temp_sensor:
            return

        temp_state = self.hass.states.get(self.temp_sensor)
        if not temp_state or temp_state.state in ("unavailable", "unknown"):
            _LOGGER.debug(
                "%s: Forced initial sync skipped - external sensor unavailable",
                self.room_name,
            )
            return

        try:
            external_temp = float(temp_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "%s: Forced initial sync skipped - invalid external sensor value: %s",
                self.room_name,
                temp_state.state,
            )
            return

        climate_state = self.hass.states.get(self.climate_entity)
        trv_temp = climate_state.attributes.get("current_temperature") if climate_state else None

        _LOGGER.info(
            "%s: Forcing initial sync (external: %.1f°C, TRV: %s)",
            self.room_name,
            external_temp,
            f"{trv_temp:.1f}°C" if trv_temp else "N/A",
        )

        self._last_external_temp_sync = None
        self._last_calibration = None

        await self._async_sync_temperature(external_temp, trv_temp or external_temp)

    async def _async_sync_temperature(
        self, external_temp: float, trv_temp: float
    ) -> None:
        """Sync external temperature to TRV using best available method."""
        _LOGGER.debug(
            "%s: Sync temperature called (external: %.1f, trv: %.1f, ext_available: %s, cal_available: %s, mqtt_available: %s)",
            self.room_name,
            external_temp,
            trv_temp,
            self._external_temp_available,
            self._calibration_available,
            self._mqtt_calibration_available,
        )
        if self._external_temp_available:
            await self._async_sync_external_temp(external_temp)
        elif self._calibration_available:
            await self._async_sync_calibration(external_temp, trv_temp)
        elif self._mqtt_calibration_available:
            await self._async_sync_mqtt_calibration(external_temp, trv_temp)
        else:
            _LOGGER.debug(
                "%s: No sync method available",
                self.room_name,
            )

    async def _async_sync_external_temp(self, external_temp: float) -> None:
        """Sync external temperature directly to TRV."""
        if not self._external_temp_available or not self._external_temp_entity:
            return

        if (
            self._last_external_temp_sync is not None
            and abs(external_temp - self._last_external_temp_sync) < 0.1
        ):
            return

        ext_state = self.hass.states.get(self._external_temp_entity)
        if not ext_state:
            return

        min_temp = ext_state.attributes.get("min", 5)
        max_temp = ext_state.attributes.get("max", 35)

        clamped_temp = max(min_temp, min(max_temp, external_temp))

        if clamped_temp != external_temp:
            _LOGGER.debug(
                "%s: External temp %.1f clamped to %.1f (range: %.1f to %.1f)",
                self.room_name,
                external_temp,
                clamped_temp,
                min_temp,
                max_temp,
            )
            external_temp = clamped_temp

        try:
            await self.hass.services.async_call(
                NUMBER_DOMAIN,
                "set_value",
                {
                    ATTR_ENTITY_ID: self._external_temp_entity,
                    "value": round(external_temp, 1),
                },
                blocking=True,
            )
            _LOGGER.info(
                "%s: Synced external temp to TRV: %.1f",
                self.room_name,
                external_temp,
            )
            self._last_external_temp_sync = external_temp
        except Exception:
            _LOGGER.exception(
                "%s: Failed to sync external temperature",
                self.room_name,
            )

    async def _async_sync_calibration(
        self, external_temp: float, trv_temp: float
    ) -> None:
        """Sync external temperature to TRV via calibration offset."""
        if not self._calibration_available or not self._calibration_entity:
            return

        cal_state = self.hass.states.get(self._calibration_entity)
        if not cal_state or cal_state.state in ("unavailable", "unknown"):
            return

        try:
            current_calibration = float(cal_state.state)
        except (ValueError, TypeError):
            current_calibration = 0.0

        raw_trv_temp = trv_temp - current_calibration
        new_calibration = round(external_temp - raw_trv_temp, 1)

        if (
            self._last_calibration is not None
            and abs(new_calibration - self._last_calibration) < 0.2
        ):
            return

        min_cal = cal_state.attributes.get("min", -10)
        max_cal = cal_state.attributes.get("max", 10)

        clamped_calibration = max(min_cal, min(max_cal, new_calibration))

        if clamped_calibration != new_calibration:
            _LOGGER.debug(
                "%s: Calibration %.1f clamped to %.1f (range: %.1f to %.1f)",
                self.room_name,
                new_calibration,
                clamped_calibration,
                min_cal,
                max_cal,
            )
            new_calibration = clamped_calibration

        try:
            await self.hass.services.async_call(
                NUMBER_DOMAIN,
                "set_value",
                {
                    ATTR_ENTITY_ID: self._calibration_entity,
                    "value": new_calibration,
                },
                blocking=True,
            )
            _LOGGER.info(
                "%s: Synced calibration offset to %.1f (External: %.1f, Raw TRV: %.1f, Prev cal: %.1f)",
                self.room_name,
                new_calibration,
                external_temp,
                raw_trv_temp,
                current_calibration,
            )
            self._last_calibration = new_calibration
        except Exception:
            _LOGGER.exception(
                "%s: Failed to sync calibration offset",
                self.room_name,
            )

    async def _async_try_mqtt_discovery(self) -> None:
        """Try to discover Zigbee2MQTT device for direct MQTT control."""
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)

        climate_entry = entity_reg.async_get(self.climate_entity)
        if not climate_entry or not climate_entry.device_id:
            _LOGGER.debug(
                "%s: Cannot discover MQTT - no device_id for climate entity",
                self.room_name,
            )
            return

        device = device_reg.async_get(climate_entry.device_id)
        if not device:
            return

        z2m_friendly_name = None
        for domain, identifier in device.identifiers:
            if domain == "mqtt":
                z2m_friendly_name = identifier
                break

        if not z2m_friendly_name:
            _LOGGER.debug(
                "%s: Device is not a Zigbee2MQTT device (identifiers: %s)",
                self.room_name,
                device.identifiers,
            )
            return

        if "mqtt" not in self.hass.services.async_services():
            _LOGGER.debug(
                "%s: MQTT service not available, cannot use direct MQTT sync",
                self.room_name,
            )
            return

        self._mqtt_friendly_name = z2m_friendly_name
        self._mqtt_calibration_available = True
        self._mqtt_control_available = True

        _LOGGER.info(
            "%s: Found Zigbee2MQTT device '%s' - will use direct MQTT for control and calibration",
            self.room_name,
            z2m_friendly_name,
        )

    async def _async_sync_mqtt_calibration(
        self, external_temp: float, trv_temp: float
    ) -> None:
        """Sync calibration offset directly via MQTT publish."""
        if not self._mqtt_calibration_available or not self._mqtt_friendly_name:
            return

        current_calibration = 0.0
        climate_state = self.hass.states.get(self.climate_entity)
        if climate_state:
            current_calibration = climate_state.attributes.get(
                "local_temperature_calibration", 0.0
            ) or 0.0

        raw_trv_temp = trv_temp - current_calibration
        new_calibration = round(external_temp - raw_trv_temp, 1)

        if (
            self._last_calibration is not None
            and abs(new_calibration - self._last_calibration) < 0.2
        ):
            return

        new_calibration = max(-12.0, min(12.0, new_calibration))

        try:
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": f"zigbee2mqtt/{self._mqtt_friendly_name}/set",
                    "payload": json.dumps({"local_temperature_calibration": new_calibration}),
                },
                blocking=True,
            )
            _LOGGER.info(
                "%s: [MQTT] Synced calibration offset to %.1f (External: %.1f, Raw TRV: %.1f, Prev cal: %.1f)",
                self.room_name,
                new_calibration,
                external_temp,
                raw_trv_temp,
                current_calibration,
            )
            self._last_calibration = new_calibration
        except Exception:
            _LOGGER.exception(
                "%s: Failed to sync calibration via MQTT",
                self.room_name,
            )

    async def async_set_trv_target_temp(self, temperature: float) -> None:
        """Set TRV target temperature using best available method."""
        if self._mqtt_control_available and self._mqtt_friendly_name:
            try:
                await self.hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": f"zigbee2mqtt/{self._mqtt_friendly_name}/set",
                        "payload": json.dumps({"occupied_heating_setpoint": temperature}),
                    },
                    blocking=True,
                )
                _LOGGER.debug(
                    "%s: [MQTT] Set target temp to %.1f°C",
                    self.room_name,
                    temperature,
                )
                return
            except Exception:
                _LOGGER.exception(
                    "%s: Failed to set target temp via MQTT, falling back to HA service",
                    self.room_name,
                )

        try:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                {
                    ATTR_ENTITY_ID: self.climate_entity,
                    ATTR_TEMPERATURE: temperature,
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.exception(
                "%s: Failed to set TRV target temperature to %.1f°C",
                self.room_name,
                temperature,
            )

    async def async_update_climate_state(
        self, *, sync_calibration: bool = False
    ) -> None:
        """Update climate state from entity."""
        state = self.hass.states.get(self.climate_entity)
        if not state:
            return

        # If TRV is unavailable, stop requesting heat to avoid running
        # the boiler based on stale data
        if state.state in ("unavailable", "unknown"):
            if self._is_on:
                _LOGGER.warning(
                    "%s: TRV is %s - stopping heat requests until it recovers",
                    self.room_name,
                    state.state,
                )
                old_needs_heat = self.needs_heat
                self._is_on = False
                if old_needs_heat and not self.needs_heat:
                    self._notify_needs_heat_changed()
            return

        old_current = self._current_temp
        old_target = self._target_temp
        old_is_on = self._is_on
        old_needs_heat = self.needs_heat

        trv_temp = state.attributes.get("current_temperature")

        if self.temp_sensor:
            temp_state = self.hass.states.get(self.temp_sensor)
            if temp_state and temp_state.state not in ("unavailable", "unknown"):
                try:
                    external_temp = float(temp_state.state)
                    self._current_temp = external_temp

                    if self.calibration_sync and sync_calibration and trv_temp is not None:
                        _LOGGER.debug(
                            "%s: Triggering temp sync (external: %.1f, trv: %.1f)",
                            self.room_name,
                            external_temp,
                            trv_temp,
                        )
                        await self._async_sync_temperature(external_temp, trv_temp)
                except (ValueError, TypeError):
                    self._current_temp = trv_temp
            else:
                self._current_temp = trv_temp
        else:
            self._current_temp = trv_temp
        self._target_temp = state.attributes.get("temperature")
        self._is_on = state.state not in ("off", "unavailable", "unknown")

        new_needs_heat = self.needs_heat

        if old_current != self._current_temp or old_target != self._target_temp:
            _LOGGER.debug(
                "%s: Temp update - Current: %.1f°C, Target: %.1f°C, Deficit: %.1f°C",
                self.room_name,
                self._current_temp or 0,
                self._target_temp or 0,
                self.temperature_deficit,
            )

        if old_target != self._target_temp:
            _LOGGER.info(
                "%s: Target temperature changed: %.1f°C -> %.1f°C",
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

        if old_needs_heat != new_needs_heat:
            _LOGGER.info(
                "%s: Heating need changed: %s -> %s",
                self.room_name,
                "NEEDS HEAT" if old_needs_heat else "NO HEAT",
                "NEEDS HEAT" if new_needs_heat else "NO HEAT",
            )

    @property
    def needs_heat(self) -> bool:
        """Return True if room needs heat."""
        if not self._is_on:
            return False
        if self._window_open_confirmed:
            return False
        if self._current_temp is None or self._target_temp is None:
            return False

        threshold = self._target_temp - self.temp_differential
        return self._current_temp < threshold

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
    def window_open_confirmed(self) -> bool:
        """Return True if window open has been confirmed after delay."""
        return self._window_open_confirmed

    @property
    def window_timer_active(self) -> bool:
        """Return True if window delay timer is running."""
        return self._window_timer is not None

    @property
    def mqtt_control_available(self) -> bool:
        """Return True if MQTT control is available for this TRV."""
        return self._mqtt_control_available

    def set_on_needs_heat_changed(self, callback: Callable[[], None]) -> None:
        """Set callback for when needs_heat state changes."""
        self._on_needs_heat_changed = callback

    def _notify_needs_heat_changed(self) -> None:
        """Notify zone that needs_heat may have changed."""
        if self._on_needs_heat_changed:
            self._on_needs_heat_changed()

    async def _async_restore_state(self) -> None:
        """Restore state from persistent storage."""
        if self._storage is None:
            return

        stored = self._storage.get_room_state(self.room_name)
        if stored is None:
            return

        from .storage import parse_datetime

        saved_at = parse_datetime(stored.get("saved_at"))
        if saved_at is None:
            return

        age_hours = (dt_util.now() - saved_at).total_seconds() / 3600
        if age_hours > 1:
            _LOGGER.debug(
                "%s: Stored state too old (%.1f hours), starting fresh",
                self.room_name,
                age_hours,
            )
            self._storage.clear_room_state(self.room_name)
            return

        self._window_open = stored.get("window_open", False)
        self._window_open_confirmed = stored.get("window_open_confirmed", False)

        _LOGGER.info(
            "%s: Restored state - window_open=%s, confirmed=%s",
            self.room_name,
            self._window_open,
            self._window_open_confirmed,
        )

        timer_remaining = stored.get("window_timer_remaining")
        if timer_remaining and timer_remaining > 0 and self._window_open:
            _LOGGER.info(
                "%s: Restoring window timer with %.0f seconds remaining",
                self.room_name,
                timer_remaining,
            )
            self._start_window_delay_timer(delay_seconds=timer_remaining)

    async def _async_save_state(self) -> None:
        """Save current state to persistent storage."""
        if self._storage is None:
            return

        window_timer_remaining = None
        if self._window_timer and self._window_timer_started:
            elapsed = (dt_util.now() - self._window_timer_started).total_seconds()
            window_timer_remaining = max(0, self.window_delay - elapsed)

        self._storage.set_room_state(
            room_name=self.room_name,
            window_open=self._window_open,
            window_open_confirmed=self._window_open_confirmed,
            window_timer_remaining=window_timer_remaining,
        )

        _LOGGER.debug(
            "%s: Saved state - window_open=%s, confirmed=%s, timer_remaining=%s",
            self.room_name,
            self._window_open,
            self._window_open_confirmed,
            window_timer_remaining,
        )
