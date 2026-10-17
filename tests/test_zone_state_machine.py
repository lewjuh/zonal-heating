"""Tests for the zone state machine."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.zonal_heating.room_state_machine import RoomStateMachine
from custom_components.zonal_heating.zone_state_machine import ZoneStateMachine

ZONE = "climate.upstairs"
TRV = "climate.bedroom_trv"


async def _make_zone(hass: HomeAssistant, room_temp: float) -> ZoneStateMachine:
    hass.states.async_set(
        TRV, "heat", {"current_temperature": room_temp, "temperature": 21.0}
    )
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    zone = ZoneStateMachine(hass, "Upstairs", ZONE, [room])
    await zone.async_start()
    return zone


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
