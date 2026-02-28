"""The zonal_heating integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CALIBRATION_SYNC,
    CONF_MIN_CYCLE_TIME,
    CONF_ROOMS,
    CONF_SETTINGS,
    CONF_TEMP_DIFFERENTIAL,
    CONF_TEMP_SENSOR,
    CONF_TRV_ENTITY,
    CONF_WINDOW_DELAY,
    CONF_WINDOW_SENSORS,
    CONF_ZONE_THERMOSTAT,
    CONF_ZONES,
    DEFAULT_CALIBRATION_SYNC,
    DEFAULT_MIN_CYCLE_TIME,
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
        "coordinators": {},
        "storage": storage,
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

    storage = hass.data[DOMAIN][entry.entry_id]["storage"]
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    window_delay = settings.get(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)
    min_cycle_time = settings.get(CONF_MIN_CYCLE_TIME, DEFAULT_MIN_CYCLE_TIME)
    temp_differential = settings.get(CONF_TEMP_DIFFERENTIAL, DEFAULT_TEMP_DIFFERENTIAL)
    calibration_sync = settings.get(CONF_CALIBRATION_SYNC, DEFAULT_CALIBRATION_SYNC)

    for zone_idx, zone in enumerate(zones):
        zone_name = zone.get("name", f"Zone {zone_idx}")
        zone_climate = zone.get(CONF_ZONE_THERMOSTAT)

        room_state_machines = []
        for room in zone.get(CONF_ROOMS, []):
            room_name = room.get("name", "")
            trv_entity = room.get(CONF_TRV_ENTITY)
            temp_sensor = room.get(CONF_TEMP_SENSOR)
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
                temp_sensor=temp_sensor,
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

        zone_sm = ZoneStateMachine(
            hass=hass,
            zone_name=zone_name,
            zone_climate=zone_climate,
            rooms=room_state_machines,
            min_cycle_time=min_cycle_time,
            storage=storage,
        )

        try:
            await zone_sm.async_start()
        except Exception:
            _LOGGER.exception(
                "Failed to start zone state machine for %s - zone will be unavailable",
                zone_name,
            )
            continue

        coordinators[zone_name] = zone_sm

        _LOGGER.info("Started zone state machine for: %s", zone_name)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Register the Lovelace card as a static resource."""
    if DOMAIN in hass.data and hass.data[DOMAIN].get("card_registered"):
        return

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["card_registered"] = True

    www_path = Path(__file__).parent / "www"
    card_file = www_path / "zonal-heating-card.js"
    card_url = f"/{DOMAIN}/zonal-heating-card.js"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(card_url, str(card_file), cache_headers=False)]
    )

    # Register with Lovelace frontend using file mtime for cache-busting
    version = str(int(card_file.stat().st_mtime))
    add_extra_js_url(hass, f"{card_url}?v={version}")

    _LOGGER.info(
        "Registered zonal-heating-card at %s (v=%s)", card_url, version
    )


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
        hass.data[DOMAIN].pop(entry.entry_id)

        _LOGGER.info(
            "Zonal heating integration unloaded successfully for entry %s",
            entry.entry_id,
        )

    return unload_ok
