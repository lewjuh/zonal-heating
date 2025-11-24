"""The zonal_heating integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AWAY_TEMPERATURE,
    CONF_MIN_CYCLE_TIME,
    CONF_PERSON_ENTITIES,
    CONF_ROOMS,
    CONF_SETTINGS,
    CONF_TEMP_DIFFERENTIAL,
    CONF_TRV_ENTITY,
    CONF_WINDOW_DELAY,
    CONF_WINDOW_SENSORS,
    CONF_ZONE_THERMOSTAT,
    CONF_ZONES,
    DEFAULT_AWAY_TEMPERATURE,
    DEFAULT_MIN_CYCLE_TIME,
    DEFAULT_TEMP_DIFFERENTIAL,
    DEFAULT_WINDOW_DELAY,
    DOMAIN,
    PLATFORMS,
)
from .room_state_machine import RoomStateMachine
from .zone_state_machine import ZoneStateMachine

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up zonal_heating from a config entry."""
    _LOGGER.debug("Setting up zonal_heating integration for entry %s", entry.entry_id)

    # Initialize storage for this entry
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "zone_states": {},  # Track last zone thermostat states
        "coordinators": {},  # Will hold zone coordinators
    }

    # Forward setup to climate platform (this creates the entities)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Now set up zone coordinators after entities are created
    await _async_setup_coordinators(hass, entry)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Zonal heating integration setup complete for entry %s", entry.entry_id
    )
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_setup_coordinators(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up zone state machines."""
    zones = entry.data.get(CONF_ZONES, [])

    # Get settings from options (if updated) or data (initial config)
    if entry.options:
        settings = entry.options
    else:
        settings = entry.data.get(CONF_SETTINGS, {})

    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    window_delay = settings.get(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)
    min_cycle_time = settings.get(CONF_MIN_CYCLE_TIME, DEFAULT_MIN_CYCLE_TIME)
    temp_differential = settings.get(CONF_TEMP_DIFFERENTIAL, DEFAULT_TEMP_DIFFERENTIAL)
    person_entities = settings.get(CONF_PERSON_ENTITIES, [])
    away_temperature = settings.get(CONF_AWAY_TEMPERATURE, DEFAULT_AWAY_TEMPERATURE)

    for zone_idx, zone in enumerate(zones):
        zone_name = zone.get("name", f"Zone {zone_idx}")
        zone_climate = zone.get(CONF_ZONE_THERMOSTAT)

        # Create room state machines for this zone
        room_state_machines = []
        for room in zone.get(CONF_ROOMS, []):
            room_name = room.get("name", "")
            trv_entity = room.get(CONF_TRV_ENTITY)
            window_sensors = room.get(CONF_WINDOW_SENSORS, [])

            if not trv_entity:
                _LOGGER.warning("Room %s has no TRV entity, skipping", room_name)
                continue

            room_sm = RoomStateMachine(
                hass=hass,
                room_name=room_name,
                climate_entity=trv_entity,
                window_sensors=window_sensors,
                window_delay=window_delay,
                temp_differential=temp_differential,
            )
            room_state_machines.append(room_sm)

        if not room_state_machines:
            _LOGGER.warning(
                "No room state machines created for zone %s, skipping",
                zone_name,
            )
            continue

        # Create and start zone state machine
        zone_sm = ZoneStateMachine(
            hass=hass,
            zone_name=zone_name,
            zone_climate=zone_climate,
            rooms=room_state_machines,
            min_cycle_time=min_cycle_time,
            person_entities=person_entities,
            away_temperature=away_temperature,
        )

        await zone_sm.async_start()
        coordinators[zone_name] = zone_sm

        _LOGGER.info("Started zone state machine for: %s", zone_name)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading zonal_heating integration for entry %s", entry.entry_id)

    # Stop all coordinators
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    for coordinator in coordinators.values():
        await coordinator.async_stop()

    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info(
            "Zonal heating integration unloaded successfully for entry %s",
            entry.entry_id,
        )

    return unload_ok
