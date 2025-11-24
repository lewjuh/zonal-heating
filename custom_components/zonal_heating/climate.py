"""Climate platform for zonal_heating integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_ON,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_AWAY_MODE,
    ATTR_HEAT_REQUESTING,
    ATTR_PEOPLE_HOME,
    ATTR_PRIORITY,
    ATTR_WINDOW_OPEN,
    ATTR_ZONE_ACTIVE,
    CONF_PRIORITY,
    CONF_ROOMS,
    CONF_SETTINGS,
    CONF_TRV_ENTITY,
    CONF_WINDOW_SENSORS,
    CONF_ZONES,
    DEFAULT_PRIORITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zonal heating climate entities from a config entry."""
    _LOGGER.debug(
        "Setting up zonal_heating climate platform for entry %s", entry.entry_id
    )

    zones = entry.data.get(CONF_ZONES, [])
    settings = entry.data.get(CONF_SETTINGS, {})

    # Create climate entities for each room
    entities = []
    for zone_idx, zone in enumerate(zones):
        zone_name = zone.get("name", f"Zone {zone_idx}")
        zone_thermostat = zone.get("zone_thermostat")

        for room_idx, room in enumerate(zone.get(CONF_ROOMS, [])):
            room_name = room.get("name", f"Room {room_idx}")
            trv_entity = room.get(CONF_TRV_ENTITY)
            window_sensors = room.get(CONF_WINDOW_SENSORS, [])
            priority = room.get(CONF_PRIORITY, DEFAULT_PRIORITY)

            _LOGGER.debug(
                "Creating climate entity for %s in %s (TRV: %s)",
                room_name,
                zone_name,
                trv_entity,
            )

            entity = ZonalHeatingClimate(
                hass=hass,
                entry_id=entry.entry_id,
                zone_name=zone_name,
                zone_thermostat=zone_thermostat,
                room_name=room_name,
                trv_entity=trv_entity,
                window_sensors=window_sensors,
                priority=priority,
                settings=settings,
            )
            entities.append(entity)

    async_add_entities(entities)
    _LOGGER.info(
        "Zonal heating: Created %d climate entities for entry %s",
        len(entities),
        entry.entry_id,
    )


class ZonalHeatingClimate(ClimateEntity, RestoreEntity):
    """Representation of a Zonal Heating virtual climate entity."""

    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_name: str,
        zone_thermostat: str,
        room_name: str,
        trv_entity: str,
        window_sensors: list[str],
        priority: int,
        settings: dict[str, Any],
    ) -> None:
        """Initialize the zonal heating climate entity."""
        self.hass = hass
        self._entry_id = entry_id
        self._zone_name = zone_name
        self._zone_thermostat = zone_thermostat
        self._room_name = room_name
        self._trv_entity = trv_entity
        self._window_sensors = window_sensors
        self._priority = priority
        self._settings = settings

        # Entity state
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_target_temperature = 20.0
        self._attr_current_temperature = None

        # Tracking state
        self._window_open = False
        self._zone_active = False
        self._heat_requesting = False

        # Entity attributes
        self._attr_unique_id = f"{entry_id}_{room_name.lower().replace(' ', '_')}"
        self._attr_name = f"Zonal Heating {room_name}"
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore previous state
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_hvac_mode = (
                HVACMode(last_state.state)
                if last_state.state in self._attr_hvac_modes
                else HVACMode.HEAT
            )
            self._attr_target_temperature = last_state.attributes.get(
                ATTR_TEMPERATURE, 20.0
            )
            self._priority = last_state.attributes.get(ATTR_PRIORITY, self._priority)

        # Track TRV state changes
        async_track_state_change_event(
            self.hass, [self._trv_entity], self._async_trv_changed
        )

        # Track window sensor state changes
        if self._window_sensors:
            async_track_state_change_event(
                self.hass, self._window_sensors, self._async_window_changed
            )

        # Track zone thermostat state changes
        async_track_state_change_event(
            self.hass, [self._zone_thermostat], self._async_zone_thermostat_changed
        )

        # Initial update
        await self._async_update_from_trv()
        self._async_update_window_state()
        self._async_update_zone_active()

        # Note: Initial window state is handled by room state machine with proper delay

    @callback
    def _async_trv_changed(self, event) -> None:
        """Handle TRV state changes."""
        self.hass.async_create_task(self._async_update_from_trv())

    @callback
    def _async_window_changed(self, event) -> None:
        """Handle window sensor state changes."""
        old_window_state = self._window_open
        self._async_update_window_state()
        new_window_state = self._window_open

        # Note: TRV control is handled by room state machine with proper delay
        # We just update the display state here
        if old_window_state != new_window_state:
            _LOGGER.debug(
                "%s: Window state changed: %s",
                self._attr_name,
                "OPEN" if new_window_state else "CLOSED",
            )

        self.async_write_ha_state()

    @callback
    def _async_zone_thermostat_changed(self, event) -> None:
        """Handle zone thermostat state changes."""
        self._async_update_zone_active()
        self.async_write_ha_state()

    async def _async_update_from_trv(self) -> None:
        """Update current temperature and heat request status from TRV."""
        trv_state = self.hass.states.get(self._trv_entity)
        if trv_state and trv_state.attributes:
            self._attr_current_temperature = trv_state.attributes.get(
                "current_temperature"
            )

            # Determine if TRV is requesting heat
            # TRV requests heat when it's in HEAT mode and current < target
            trv_current = trv_state.attributes.get("current_temperature")
            trv_target = trv_state.attributes.get("temperature")
            trv_hvac_mode = trv_state.state

            old_heat_requesting = self._heat_requesting

            if (
                trv_hvac_mode == HVACMode.HEAT
                and trv_current is not None
                and trv_target is not None
                and trv_current < trv_target
            ):
                self._heat_requesting = True
            else:
                self._heat_requesting = False

            # Log heat requesting changes
            if old_heat_requesting != self._heat_requesting:
                _LOGGER.debug(
                    "%s: Heat requesting changed: %s (TRV: %s, Current: %.1f°C, Target: %.1f°C)",
                    self._attr_name,
                    "YES" if self._heat_requesting else "NO",
                    trv_hvac_mode,
                    trv_current or 0,
                    trv_target or 0,
                )

            self.async_write_ha_state()

    @callback
    def _async_update_window_state(self) -> None:
        """Update window open state from sensors."""
        self._window_open = any(
            self.hass.states.is_state(sensor, STATE_ON)
            for sensor in self._window_sensors
        )

    @callback
    def _async_update_zone_active(self) -> None:
        """Update zone active state from zone thermostat."""
        zone_state = self.hass.states.get(self._zone_thermostat)
        if zone_state:
            self._zone_active = zone_state.state == HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action."""
        if self._attr_hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        if self._window_open:
            return HVACAction.OFF

        if self._zone_active and self._heat_requesting:
            return HVACAction.HEATING

        if self._heat_requesting:
            return HVACAction.IDLE  # Requesting but zone not active

        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        # Get zone state machine for away mode info
        zone_coordinator = None
        if DOMAIN in self.hass.data and self._entry_id in self.hass.data[DOMAIN]:
            coordinators = self.hass.data[DOMAIN][self._entry_id].get("coordinators", {})
            zone_coordinator = coordinators.get(self._zone_name)

        attrs = {
            ATTR_ZONE_ACTIVE: self._zone_active,
            ATTR_WINDOW_OPEN: self._window_open,
            ATTR_HEAT_REQUESTING: self._heat_requesting,
            ATTR_PRIORITY: self._priority,
            "zone_name": self._zone_name,
            "trv_entity": self._trv_entity,
        }

        # Add away mode info if zone coordinator available
        if zone_coordinator:
            attrs[ATTR_AWAY_MODE] = zone_coordinator.away_mode
            if zone_coordinator.person_entities:
                attrs[ATTR_PEOPLE_HOME] = zone_coordinator.people_home_count

        # Determine why active/inactive
        if zone_coordinator and zone_coordinator.away_mode:
            attrs["why_inactive"] = "Away mode - low power"
        elif self.hvac_action == HVACAction.HEATING:
            attrs["why_active"] = "Heating to target temperature"
        elif self.hvac_action == HVACAction.IDLE and self._heat_requesting:
            attrs["why_inactive"] = "Waiting for zone to activate"
        elif self._attr_hvac_mode == HVACMode.OFF:
            attrs["why_inactive"] = "Climate turned off"
        elif self._window_open:
            attrs["why_inactive"] = "Window open"
        elif (
            self._attr_current_temperature is not None
            and self._attr_target_temperature is not None
            and self._attr_current_temperature >= self._attr_target_temperature
        ):
            attrs["why_inactive"] = "Target temperature reached"
        elif not self._zone_active:
            attrs["why_inactive"] = "Zone not active"
        else:
            attrs["why_inactive"] = "Idle"

        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        self._attr_target_temperature = temperature
        self.async_write_ha_state()
        _LOGGER.debug(
            "%s: Set target temperature to %.1f°C",
            self._attr_name,
            temperature,
        )

        # Forward temperature to the actual TRV
        _LOGGER.debug(
            "%s: Forwarding temperature %.1f°C to TRV %s",
            self._attr_name,
            temperature,
            self._trv_entity,
        )
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_temperature",
            {
                ATTR_ENTITY_ID: self._trv_entity,
                ATTR_TEMPERATURE: temperature,
            },
            blocking=False,
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if hvac_mode not in self._attr_hvac_modes:
            _LOGGER.error("%s: Unsupported HVAC mode: %s", self._attr_name, hvac_mode)
            return

        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()
        _LOGGER.debug("%s: Set HVAC mode to %s", self._attr_name, hvac_mode)

        # Forward HVAC mode to the actual TRV
        _LOGGER.debug(
            "%s: Forwarding HVAC mode %s to TRV %s",
            self._attr_name,
            hvac_mode,
            self._trv_entity,
        )
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_hvac_mode",
            {
                ATTR_ENTITY_ID: self._trv_entity,
                "hvac_mode": hvac_mode,
            },
            blocking=False,
        )
