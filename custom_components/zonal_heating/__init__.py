"""The zonal_heating integration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AWAY_MODE_DELAY,
    CONF_AWAY_TEMPERATURE,
    CONF_CALIBRATION_SYNC,
    CONF_MIN_CYCLE_TIME,
    CONF_OVERHEAT_THRESHOLD,
    CONF_PERSON_ENTITIES,
    CONF_ROOMS,
    CONF_SETTINGS,
    CONF_TEMP_DIFFERENTIAL,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_DELAY,
    CONF_WINDOW_SENSORS,
    CONF_ZONE_THERMOSTAT,
    CONF_ZONES,
    DEFAULT_AWAY_MODE_DELAY,
    DEFAULT_AWAY_TEMPERATURE,
    DEFAULT_CALIBRATION_SYNC,
    DEFAULT_MIN_CYCLE_TIME,
    DEFAULT_OVERHEAT_THRESHOLD,
    DEFAULT_SENSOR_STALE_THRESHOLD,
    DEFAULT_TEMP_DIFFERENTIAL,
    DEFAULT_WINDOW_DELAY,
    DOMAIN,
    PLATFORMS,
)
from .room_state_machine import RoomStateMachine
from .storage import ZonalHeatingStorage
from .zone_state_machine import ZoneStateMachine

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up zonal_heating from a config entry."""
    _LOGGER.debug("Setting up zonal_heating integration for entry %s", entry.entry_id)

    # Register the Lovelace card
    await _async_register_card(hass)

    # Initialize persistent storage for this entry
    storage = ZonalHeatingStorage(hass, entry.entry_id)
    await storage.async_load()

    # Initialize storage for this entry
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "zone_states": {},  # Track last zone thermostat states
        "coordinators": {},  # Will hold zone coordinators
        "storage": storage,  # Persistent storage instance
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


async def _async_wait_for_entity(
    hass: HomeAssistant, entity_id: str, timeout: float = 30
) -> bool:
    """Wait for an entity to become available."""
    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        state = hass.states.get(entity_id)
        if state and state.state not in ("unavailable", "unknown"):
            return True
        await asyncio.sleep(0.5)
    return False


async def _async_setup_coordinators(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up zone state machines."""
    zones = entry.data.get(CONF_ZONES, [])

    # Get settings from options (if updated) or data (initial config)
    if entry.options:
        settings = entry.options
    else:
        settings = entry.data.get(CONF_SETTINGS, {})

    # Get storage instance
    storage = hass.data[DOMAIN][entry.entry_id]["storage"]

    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    window_delay = settings.get(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)
    min_cycle_time = settings.get(CONF_MIN_CYCLE_TIME, DEFAULT_MIN_CYCLE_TIME)
    temp_differential = settings.get(CONF_TEMP_DIFFERENTIAL, DEFAULT_TEMP_DIFFERENTIAL)
    overheat_threshold = settings.get(CONF_OVERHEAT_THRESHOLD, DEFAULT_OVERHEAT_THRESHOLD)
    person_entities = settings.get(CONF_PERSON_ENTITIES, [])
    away_temperature = settings.get(CONF_AWAY_TEMPERATURE, DEFAULT_AWAY_TEMPERATURE)
    away_mode_delay = settings.get(CONF_AWAY_MODE_DELAY, DEFAULT_AWAY_MODE_DELAY)
    calibration_sync = settings.get(CONF_CALIBRATION_SYNC, DEFAULT_CALIBRATION_SYNC)

    for zone_idx, zone in enumerate(zones):
        zone_name = zone.get("name", f"Zone {zone_idx}")
        zone_climate = zone.get(CONF_ZONE_THERMOSTAT)

        # Wait for zone thermostat entity to be available
        if zone_climate:
            _LOGGER.debug(
                "Waiting for zone thermostat entity %s to become available",
                zone_climate,
            )
            if not await _async_wait_for_entity(hass, zone_climate, timeout=60):
                _LOGGER.warning(
                    "Zone %s: Zone thermostat %s not available after 60s, "
                    "will retry when entity becomes available",
                    zone_name,
                    zone_climate,
                )

        # Create room state machines for this zone
        room_state_machines = []
        for room in zone.get(CONF_ROOMS, []):
            room_name = room.get("name", "")
            trv_entity = room.get(CONF_TRV_ENTITY)
            temp_sensor = room.get(CONF_TEMP_SENSOR)
            window_sensors = room.get(CONF_WINDOW_SENSORS, [])

            if not trv_entity:
                _LOGGER.warning("Room %s has no TRV entity, skipping", room_name)
                continue

            # Wait for TRV entity to be available
            if not await _async_wait_for_entity(hass, trv_entity, timeout=30):
                _LOGGER.warning(
                    "Room %s: TRV entity %s not available after 30s, "
                    "will retry when entity becomes available",
                    room_name,
                    trv_entity,
                )

            room_sm = RoomStateMachine(
                hass=hass,
                room_name=room_name,
                climate_entity=trv_entity,
                window_sensors=window_sensors,
                window_delay=window_delay,
                temp_differential=temp_differential,
                overheat_threshold=overheat_threshold,
                temp_sensor=temp_sensor,
                stale_sensor_threshold=DEFAULT_SENSOR_STALE_THRESHOLD,
                calibration_sync=calibration_sync,
                storage=storage,
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
            away_mode_delay=away_mode_delay,
            storage=storage,
        )

        await zone_sm.async_start()
        coordinators[zone_name] = zone_sm

        _LOGGER.info("Started zone state machine for: %s", zone_name)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Register the Lovelace card as a static resource."""
    if DOMAIN in hass.data and hass.data[DOMAIN].get("card_registered"):
        return

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["card_registered"] = True

    www_path = Path(__file__).parent / "www"
    card_url = f"/{DOMAIN}/zonal-heating-card.js"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(card_url, str(www_path / "zonal-heating-card.js"), False)]
    )

    _LOGGER.info("Registered zonal-heating-card at %s", card_url)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading zonal_heating integration for entry %s", entry.entry_id)

    # Stop all coordinators (this triggers state save in each state machine)
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    for coordinator in coordinators.values():
        await coordinator.async_stop()

    # Save persistent storage
    storage = hass.data[DOMAIN][entry.entry_id].get("storage")
    if storage:
        await storage.async_save()
        _LOGGER.debug("Saved persistent state for entry %s", entry.entry_id)

    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info(
            "Zonal heating integration unloaded successfully for entry %s",
            entry.entry_id,
        )

    return unload_ok
