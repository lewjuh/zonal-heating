"""Tests for the room state machine."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.zonal_heating.room_state_machine import RoomStateMachine
from custom_components.zonal_heating.storage import ZonalHeatingStorage

TRV = "climate.bedroom_trv"
WINDOW = "binary_sensor.bedroom_window"


def _set_trv(
    hass: HomeAssistant,
    current: float,
    target: float = 21.0,
    mode: str = "heat",
    **attrs,
) -> None:
    hass.states.async_set(
        TRV, mode, {"current_temperature": current, "temperature": target, **attrs}
    )


def _register_trv_device(hass: HomeAssistant, *entities: tuple[str, str]) -> None:
    """Register the TRV and its sibling entities on one device, as Z2M does."""
    entry = MockConfigEntry(domain="mqtt")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mqtt", "bedroom_trv")}
    )
    ent_reg = er.async_get(hass)
    for domain, object_id in (("climate", "bedroom_trv"), *entities):
        ent_reg.async_get_or_create(
            domain,
            "mqtt",
            object_id,
            suggested_object_id=object_id,
            config_entry=entry,
            device_id=device.id,
        )


async def _set_and_update(room: RoomStateMachine, hass: HomeAssistant, current: float) -> None:
    _set_trv(hass, current)
    await hass.async_block_till_done()
    await room.async_update_climate_state()


async def test_heat_demand_has_hysteresis(hass: HomeAssistant) -> None:
    """Demand starts below target - differential and holds until target."""
    _set_trv(hass, 20.9)
    room = RoomStateMachine(hass, "Bedroom", TRV, [], temp_differential=0.25)
    await room.async_start()

    assert not room.needs_heat

    await _set_and_update(room, hass, 20.7)
    assert room.needs_heat

    await _set_and_update(room, hass, 20.9)
    assert room.needs_heat, "should keep heating inside the deadband"

    await _set_and_update(room, hass, 21.0)
    assert not room.needs_heat

    await _set_and_update(room, hass, 20.8)
    assert not room.needs_heat, "should not restart inside the deadband"

    await room.async_stop()


async def test_trv_off_clears_demand(hass: HomeAssistant) -> None:
    """A TRV switched off never asks for heat."""
    _set_trv(hass, 18.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    await room.async_start()
    assert room.needs_heat

    _set_trv(hass, 18.0, mode="off")
    await room.async_update_climate_state()
    assert not room.needs_heat

    await room.async_stop()


async def test_stale_confirmed_window_cleared_on_start(hass: HomeAssistant) -> None:
    """A window confirmed open before a restart is cleared if it is now closed."""
    storage = ZonalHeatingStorage(hass, "entry")
    await storage.async_load()
    storage.set_room_state("Bedroom", True, True, None)

    hass.states.async_set(WINDOW, "off")
    _set_trv(hass, 18.0)

    room = RoomStateMachine(hass, "Bedroom", TRV, [WINDOW], storage=storage)
    await room.async_start()

    assert not room.window_open_confirmed
    assert room.needs_heat

    await room.async_stop()


async def test_restored_window_timer_keeps_remaining_time(hass: HomeAssistant) -> None:
    """A restored window timer is not restarted from the full delay."""
    storage = ZonalHeatingStorage(hass, "entry")
    await storage.async_load()
    storage.set_room_state("Bedroom", True, False, 5.0)

    hass.states.async_set(WINDOW, "on")
    _set_trv(hass, 18.0)

    room = RoomStateMachine(
        hass, "Bedroom", TRV, [WINDOW], window_delay=300, storage=storage
    )
    await room.async_start()

    assert room.window_timer_active
    assert room._window_timer_delay == 5.0

    await room.async_stop()


async def test_window_confirm_and_close(hass: HomeAssistant) -> None:
    """Confirmed window suppresses demand; closing resumes it."""
    hass.states.async_set(WINDOW, "off")
    _set_trv(hass, 18.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [WINDOW], window_delay=30)
    await room.async_start()
    assert room.needs_heat

    hass.states.async_set(WINDOW, "on")
    await hass.async_block_till_done()
    assert room.window_timer_active
    assert room.needs_heat

    await room._async_window_delay_expired()
    assert not room.needs_heat

    hass.states.async_set(WINDOW, "off")
    await hass.async_block_till_done()
    assert not room.window_open_confirmed
    assert room.needs_heat

    await room.async_stop()


async def test_calibration_waits_for_fresh_trv_reading(hass: HomeAssistant) -> None:
    """Calibration is not recomputed from a TRV reading older than the last offset change."""
    calls = async_mock_service(hass, "number", "set_value")
    cal_entity = "number.bedroom_trv_local_temperature_calibration"

    _set_trv(hass, 19.0)
    await hass.async_block_till_done()
    hass.states.async_set(cal_entity, "1.0", {"min": -5, "max": 5})
    await hass.async_block_till_done()

    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    room._calibration_entity = cal_entity
    room._calibration_available = True

    await room._async_sync_calibration(external_temp=21.0, trv_temp=19.0)
    assert not calls

    _set_trv(hass, 20.0)
    await hass.async_block_till_done()
    await room._async_sync_calibration(external_temp=21.0, trv_temp=20.0)
    assert len(calls) == 1
    assert calls[0].data["value"] == 2.0


async def test_set_target_uses_climate_service(hass: HomeAssistant) -> None:
    """Target changes always go through the TRV's climate entity."""
    calls = async_mock_service(hass, "climate", "set_temperature")
    _set_trv(hass, 19.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [])

    await room.async_set_trv_target_temp(22.5)

    assert len(calls) == 1
    assert calls[0].data == {"entity_id": TRV, "temperature": 22.5}


async def test_calibration_found_while_entity_still_unknown(hass: HomeAssistant) -> None:
    """Discovery uses the registry, so an entity with no value yet at startup is still found."""
    cal_entity = "number.bedroom_trv_local_temperature_calibration"
    _register_trv_device(hass, ("number", "bedroom_trv_local_temperature_calibration"))
    hass.states.async_set(cal_entity, "unknown")
    hass.states.async_set("sensor.bedroom_temp", "20.0")
    _set_trv(hass, 19.0)

    room = RoomStateMachine(
        hass, "Bedroom", TRV, [], temp_sensor="sensor.bedroom_temp", calibration_sync=True
    )
    await room.async_start()

    assert room._calibration_available
    assert room._calibration_entity == cal_entity
    await room.async_stop()


async def test_external_input_preferred_and_selector_set_once_ready(
    hass: HomeAssistant,
) -> None:
    """External temp input wins over calibration, and the sensor selector is switched lazily."""
    ext_entity = "number.bedroom_trv_external_temperature_input"
    selector = "select.bedroom_trv_temperature_sensor_select"
    _register_trv_device(
        hass,
        ("number", "bedroom_trv_local_temperature_calibration"),
        ("number", "bedroom_trv_external_temperature_input"),
        ("select", "bedroom_trv_temperature_sensor_select"),
    )
    set_value = async_mock_service(hass, "number", "set_value")
    select_option = async_mock_service(hass, "select", "select_option")
    hass.states.async_set(ext_entity, "unknown")
    hass.states.async_set(selector, "unknown")
    _set_trv(hass, 19.0)

    room = RoomStateMachine(hass, "Bedroom", TRV, [], calibration_sync=True)
    room.temp_sensor = "sensor.bedroom_temp"
    await room._async_discover_sync_entities()
    assert room._external_temp_entity == ext_entity

    await room._async_sync_external_temp(20.5)
    assert not set_value and not select_option

    hass.states.async_set(ext_entity, "19.0", {"min": 0, "max": 35})
    hass.states.async_set(selector, "internal", {"options": ["internal", "external"]})
    await room._async_sync_external_temp(20.5)

    assert select_option[0].data == {"entity_id": selector, "option": "external"}
    assert set_value[0].data == {"entity_id": ext_entity, "value": 20.5}


async def test_room_not_counted_when_trv_reports_idle(hass: HomeAssistant) -> None:
    """A room below target whose TRV has closed its valve does not hold the zone on."""
    hass.states.async_set("sensor.bedroom_temp", "18.0")
    _set_trv(hass, 21.5, hvac_action="idle")
    room = RoomStateMachine(hass, "Bedroom", TRV, [], temp_sensor="sensor.bedroom_temp")
    await room.async_start()

    assert room.needs_heat
    assert room.trv_satisfied
    assert not room.calls_for_heat

    _set_trv(hass, 21.5, hvac_action="heating")
    await room.async_update_climate_state()
    assert room.calls_for_heat
    await room.async_stop()


async def test_trv_reading_used_when_no_hvac_action(hass: HomeAssistant) -> None:
    """Without hvac_action, a TRV reading at or above its target counts as satisfied."""
    hass.states.async_set("sensor.bedroom_temp", "18.0")
    _set_trv(hass, 21.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [], temp_sensor="sensor.bedroom_temp")
    await room.async_start()

    assert room.needs_heat
    assert not room.calls_for_heat

    _set_trv(hass, 20.5)
    await room.async_update_climate_state()
    assert room.calls_for_heat
    await room.async_stop()


async def test_stalled_room_is_ignored_then_retried(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A room that doesn't warm for an hour of zone heating is dropped, then retried."""
    _set_trv(hass, 18.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    await room.async_start()

    room.update_demand_progress(zone_on=True)
    freezer.tick(timedelta(minutes=59))
    room.update_demand_progress(zone_on=True)
    assert room.calls_for_heat

    freezer.tick(timedelta(minutes=2))
    room.update_demand_progress(zone_on=True)
    assert room.demand_stalled
    assert not room.calls_for_heat

    freezer.tick(timedelta(hours=2))
    room.update_demand_progress(zone_on=True)
    assert not room.demand_stalled
    assert room.calls_for_heat
    await room.async_stop()


async def test_warming_room_does_not_stall(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Steady progress keeps resetting the stall window."""
    _set_trv(hass, 18.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    await room.async_start()

    room.update_demand_progress(zone_on=True)
    for temp in (18.2, 18.4, 18.6):
        freezer.tick(timedelta(minutes=50))
        await _set_and_update(room, hass, temp)
        room.update_demand_progress(zone_on=True)

    assert not room.demand_stalled
    await room.async_stop()


async def test_target_change_clears_stall(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Changing the target gives a stalled room a fresh start."""
    _set_trv(hass, 18.0)
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    await room.async_start()
    room.update_demand_progress(zone_on=True)
    freezer.tick(timedelta(minutes=61))
    room.update_demand_progress(zone_on=True)
    assert room.demand_stalled

    _set_trv(hass, 18.0, target=22.0)
    await room.async_update_climate_state()
    assert not room.demand_stalled
    await room.async_stop()
