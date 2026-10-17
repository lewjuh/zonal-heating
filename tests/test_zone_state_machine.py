"""Tests for the zone state machine."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from custom_components.zonal_heating.room_state_machine import RoomStateMachine
from custom_components.zonal_heating.zone_state_machine import ZoneStateMachine

ZONE = "climate.upstairs"
TRV = "climate.bedroom_trv"


async def _make_zone(hass: HomeAssistant, room_temp: float, **zone_kwargs) -> ZoneStateMachine:
    hass.states.async_set(
        TRV, "heat", {"current_temperature": room_temp, "temperature": 21.0}
    )
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    zone = ZoneStateMachine(hass, "Upstairs", ZONE, [room], **zone_kwargs)
    await zone.async_start()
    return zone


def _end_grace_period(zone: ZoneStateMachine) -> None:
    zone._startup_time = dt_util.now() - timedelta(hours=1)


async def _set_room_temp(hass: HomeAssistant, zone: ZoneStateMachine, temp: float) -> None:
    hass.states.async_set(TRV, "heat", {"current_temperature": temp, "temperature": 21.0})
    await zone.rooms[0].async_update_climate_state()
    await zone._async_evaluate_zone()


async def test_turn_on_caps_target_at_max_temp(hass: HomeAssistant) -> None:
    """The boost target respects the thermostat's max_temp and heat is set explicitly."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(
        ZONE, "off", {"current_temperature": 21.0, "min_temp": 5, "max_temp": 25}
    )

    zone = await _make_zone(hass, room_temp=18.0)

    assert len(set_mode) == 1
    assert set_mode[0].data == {"entity_id": ZONE, "hvac_mode": "heat"}
    assert len(set_temp) == 1
    assert set_temp[0].data == {"entity_id": ZONE, "temperature": 25}
    await zone.async_stop()


async def test_turn_on_works_when_set_temperature_ignores_hvac_mode(
    hass: HomeAssistant,
) -> None:
    """A thermostat that ignores hvac_mode in set_temperature (meross_lan) still turns on."""

    async def set_hvac_mode(call: ServiceCall) -> None:
        state = hass.states.get(ZONE)
        hass.states.async_set(ZONE, call.data["hvac_mode"], state.attributes)

    async def set_temperature(call: ServiceCall) -> None:
        state = hass.states.get(ZONE)
        attrs = {**state.attributes, "temperature": call.data["temperature"]}
        hass.states.async_set(ZONE, state.state, attrs)

    hass.services.async_register("climate", "set_hvac_mode", set_hvac_mode)
    hass.services.async_register("climate", "set_temperature", set_temperature)
    hass.states.async_set(
        ZONE, "off", {"current_temperature": 19.0, "max_temp": 35}
    )

    zone = await _make_zone(hass, room_temp=18.0)

    state = hass.states.get(ZONE)
    assert state.state == "heat"
    assert state.attributes["temperature"] == 24.0
    assert zone.zone_is_on
    await zone.async_stop()


async def test_turn_on_uses_current_plus_boost(hass: HomeAssistant) -> None:
    """Without a limit in reach, the target is current + 5."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(
        ZONE, "off", {"current_temperature": 19.0, "max_temp": 35}
    )

    zone = await _make_zone(hass, room_temp=18.0)

    assert set_temp[0].data["temperature"] == 24.0
    await zone.async_stop()


async def test_auto_mode_thermostat_is_turned_off(hass: HomeAssistant) -> None:
    """A zone thermostat left in auto is switched off when no room needs heat."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(ZONE, "auto", {"current_temperature": 21.0})

    zone = await _make_zone(hass, room_temp=22.0)

    assert len(set_mode) == 1
    assert set_mode[0].data == {"entity_id": ZONE, "hvac_mode": "off"}
    await zone.async_stop()


async def test_unavailable_thermostat_is_left_alone(hass: HomeAssistant) -> None:
    """No service calls are made against an unavailable zone thermostat."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(ZONE, "unavailable")

    zone = await _make_zone(hass, room_temp=18.0)

    assert not set_temp
    assert not set_mode
    await zone.async_stop()


async def test_min_on_time_holds_zone_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A zone that just turned on stays on until min_on_time has passed."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(ZONE, "off", {"current_temperature": 19.0, "max_temp": 35})

    zone = await _make_zone(hass, room_temp=18.0, min_on_time=10, min_off_time=10)
    assert zone.zone_is_on
    _end_grace_period(zone)
    hass.states.async_set(ZONE, "heat", {"current_temperature": 19.0, "max_temp": 35})
    set_mode.clear()

    freezer.tick(timedelta(minutes=4))
    await _set_room_temp(hass, zone, 21.0)
    assert not set_mode
    assert zone.retry_timer_active

    freezer.tick(timedelta(minutes=7))
    await zone._async_evaluate_zone()
    assert set_mode[-1].data == {"entity_id": ZONE, "hvac_mode": "off"}
    await zone.async_stop()


async def test_min_off_time_holds_zone_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A zone that just turned off stays off until min_off_time has passed."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(ZONE, "heat", {"current_temperature": 19.0, "max_temp": 35})

    zone = await _make_zone(hass, room_temp=22.0, min_on_time=5, min_off_time=15)
    assert not zone.zone_is_on
    _end_grace_period(zone)
    hass.states.async_set(ZONE, "off", {"current_temperature": 19.0, "max_temp": 35})
    set_mode.clear()

    freezer.tick(timedelta(minutes=10))
    await _set_room_temp(hass, zone, 18.0)
    assert not set_mode

    freezer.tick(timedelta(minutes=6))
    await zone._async_evaluate_zone()
    assert set_mode[-1].data == {"entity_id": ZONE, "hvac_mode": "heat"}
    await zone.async_stop()


async def test_zone_ignores_room_whose_trv_is_satisfied(hass: HomeAssistant) -> None:
    """The zone is not turned on for a room whose TRV has closed its valve."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(ZONE, "off", {"current_temperature": 19.0, "max_temp": 35})
    hass.states.async_set(
        TRV,
        "heat",
        {"current_temperature": 18.0, "temperature": 21.0, "hvac_action": "idle"},
    )
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    zone = ZoneStateMachine(hass, "Upstairs", ZONE, [room])
    await zone.async_start()

    assert room.needs_heat
    assert not set_mode and not set_temp
    await zone.async_stop()
