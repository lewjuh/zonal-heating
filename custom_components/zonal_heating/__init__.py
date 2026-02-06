"""The zonal_heating integration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

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
    DEFAULT_TEMP_DIFFERENTIAL,
    DEFAULT_WINDOW_DELAY,
    DOMAIN,
    PLATFORMS,
)
from .room_state_machine import RoomStateMachine
from .scheduler import RoomScheduler
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
        "schedulers": {},  # Will hold room schedulers
        "storage": storage,  # Persistent storage instance
    }

    # Forward setup to climate platform (this creates the entities)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Now set up zone coordinators after entities are created
    await _async_setup_coordinators(hass, entry)

    # Register services
    await _async_register_services(hass, entry)

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
    hass: HomeAssistant, entity_id: str, timeout: float = 5
) -> bool:
    """Wait briefly for an entity to become available."""
    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        state = hass.states.get(entity_id)
        if state:
            return True
        await asyncio.sleep(0.2)
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

        # Brief wait for zone thermostat entity (state listeners handle late arrivals)
        if zone_climate:
            if not await _async_wait_for_entity(hass, zone_climate, timeout=5):
                _LOGGER.debug(
                    "Zone %s: Zone thermostat %s not yet available, will use state listeners",
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

            # Brief wait for TRV entity (state listeners handle late arrivals)
            if not await _async_wait_for_entity(hass, trv_entity, timeout=3):
                _LOGGER.debug(
                    "Room %s: TRV %s not yet available, will use state listeners",
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
                calibration_sync=calibration_sync,
                storage=storage,
            )
            room_state_machines.append(room_sm)

            # Create scheduler for this room
            scheduler = RoomScheduler(
                hass=hass,
                room_name=room_name,
                room_state_machine=room_sm,
                storage=storage,
            )
            room_sm.set_scheduler(scheduler)
            hass.data[DOMAIN][entry.entry_id]["schedulers"][room_name] = scheduler

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

        # Start schedulers for rooms in this zone
        schedulers = hass.data[DOMAIN][entry.entry_id]["schedulers"]
        for room_sm in room_state_machines:
            if room_sm.room_name in schedulers:
                await schedulers[room_sm.room_name].async_start()

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
        [StaticPathConfig(card_url, str(www_path / "zonal-heating-card.js"), cache_headers=False)]
    )

    _LOGGER.info("Registered zonal-heating-card at %s (cache disabled)", card_url)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading zonal_heating integration for entry %s", entry.entry_id)

    # Stop all schedulers
    schedulers = hass.data[DOMAIN][entry.entry_id].get("schedulers", {})
    for scheduler in schedulers.values():
        await scheduler.async_stop()

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


async def _async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register zonal heating services."""
    if hass.services.has_service(DOMAIN, "set_room_schedule"):
        return

    async def _find_scheduler(room_name: str) -> RoomScheduler | None:
        """Find the scheduler for a room across all entries."""
        for entry_id, data in hass.data.get(DOMAIN, {}).items():
            if isinstance(data, dict) and "schedulers" in data:
                if room_name in data["schedulers"]:
                    return data["schedulers"][room_name]
        return None

    async def _find_storage(room_name: str) -> ZonalHeatingStorage | None:
        """Find the storage instance for a room."""
        for entry_id, data in hass.data.get(DOMAIN, {}).items():
            if isinstance(data, dict) and "schedulers" in data:
                if room_name in data["schedulers"]:
                    return data.get("storage")
        return None

    async def handle_set_room_schedule(call: ServiceCall) -> None:
        """Handle set_room_schedule service call."""
        room_name = call.data.get("room_name")
        if not room_name:
            _LOGGER.error("set_room_schedule: room_name is required")
            return

        storage = await _find_storage(room_name)
        if not storage:
            _LOGGER.error("set_room_schedule: Room '%s' not found", room_name)
            return

        schedule = {
            "enabled": call.data.get("enabled", True),
            "weekday": call.data.get("weekday", []),
            "weekend": call.data.get("weekend", []),
        }

        storage.set_room_schedule(room_name, schedule)
        await storage.async_save()

        scheduler = await _find_scheduler(room_name)
        if scheduler:
            await scheduler.async_reload_schedule()

        _LOGGER.info("Set schedule for room '%s'", room_name)

    async def handle_get_room_schedule(call: ServiceCall) -> dict:
        """Handle get_room_schedule service call."""
        room_name = call.data.get("room_name")
        if not room_name:
            return {"error": "room_name is required"}

        storage = await _find_storage(room_name)
        if not storage:
            return {"error": f"Room '{room_name}' not found"}

        schedule = storage.get_room_schedule(room_name)
        if schedule:
            return {"room_name": room_name, **schedule}
        return {"room_name": room_name, "enabled": False, "weekday": [], "weekend": []}

    async def handle_delete_room_schedule(call: ServiceCall) -> None:
        """Handle delete_room_schedule service call."""
        room_name = call.data.get("room_name")
        if not room_name:
            _LOGGER.error("delete_room_schedule: room_name is required")
            return

        storage = await _find_storage(room_name)
        if not storage:
            _LOGGER.error("delete_room_schedule: Room '%s' not found", room_name)
            return

        storage.delete_room_schedule(room_name)
        await storage.async_save()

        scheduler = await _find_scheduler(room_name)
        if scheduler:
            await scheduler.async_reload_schedule()

        _LOGGER.info("Deleted schedule for room '%s'", room_name)

    async def handle_add_schedule_point(call: ServiceCall) -> None:
        """Handle add_schedule_point service call."""
        room_name = call.data.get("room_name")
        timeline = call.data.get("timeline")
        time = call.data.get("time")
        temperature = call.data.get("temperature")

        if not all([room_name, timeline, time, temperature]):
            _LOGGER.error("add_schedule_point: Missing required fields")
            return

        if timeline not in ("weekday", "weekend"):
            _LOGGER.error("add_schedule_point: timeline must be 'weekday' or 'weekend'")
            return

        storage = await _find_storage(room_name)
        if not storage:
            _LOGGER.error("add_schedule_point: Room '%s' not found", room_name)
            return

        schedule = storage.get_room_schedule(room_name) or {
            "enabled": True,
            "weekday": [],
            "weekend": [],
        }

        points = schedule.get(timeline, [])
        points = [p for p in points if p.get("time") != time]
        points.append({"time": time, "temperature": float(temperature)})
        schedule[timeline] = points

        storage.set_room_schedule(room_name, schedule)
        await storage.async_save()

        scheduler = await _find_scheduler(room_name)
        if scheduler:
            await scheduler.async_reload_schedule()

        _LOGGER.info("Added schedule point for room '%s': %s at %s", room_name, temperature, time)

    async def handle_remove_schedule_point(call: ServiceCall) -> None:
        """Handle remove_schedule_point service call."""
        room_name = call.data.get("room_name")
        timeline = call.data.get("timeline")
        time = call.data.get("time")

        if not all([room_name, timeline, time]):
            _LOGGER.error("remove_schedule_point: Missing required fields")
            return

        storage = await _find_storage(room_name)
        if not storage:
            _LOGGER.error("remove_schedule_point: Room '%s' not found", room_name)
            return

        schedule = storage.get_room_schedule(room_name)
        if not schedule:
            _LOGGER.warning("remove_schedule_point: No schedule for room '%s'", room_name)
            return

        points = schedule.get(timeline, [])
        schedule[timeline] = [p for p in points if p.get("time") != time]

        storage.set_room_schedule(room_name, schedule)
        await storage.async_save()

        scheduler = await _find_scheduler(room_name)
        if scheduler:
            await scheduler.async_reload_schedule()

        _LOGGER.info("Removed schedule point for room '%s' at %s", room_name, time)

    hass.services.async_register(
        DOMAIN, "set_room_schedule", handle_set_room_schedule
    )
    hass.services.async_register(
        DOMAIN,
        "get_room_schedule",
        handle_get_room_schedule,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "delete_room_schedule", handle_delete_room_schedule
    )
    hass.services.async_register(
        DOMAIN, "add_schedule_point", handle_add_schedule_point
    )
    hass.services.async_register(
        DOMAIN, "remove_schedule_point", handle_remove_schedule_point
    )

    _LOGGER.info("Registered zonal_heating schedule services")
