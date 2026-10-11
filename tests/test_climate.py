"""Tests for the virtual climate entity."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant

from custom_components.zonal_heating.climate import ZonalHeatingClimate

TRV = "climate.bedroom_trv"


def _entity(hass: HomeAssistant, mode: HVACMode, target: float = 21.0) -> ZonalHeatingClimate:
    entity = ZonalHeatingClimate(
        hass=hass,
        entry_id="entry",
        zone_name="Upstairs",
        zone_thermostat="climate.upstairs",
        room_name="Bedroom",
        trv_entity=TRV,
        temp_sensor=None,
        window_sensors=[],
        priority=5,
    )
    entity._attr_hvac_mode = mode
    entity._attr_target_temperature = target
    return entity


async def test_startup_sync_keeps_room_off(hass: HomeAssistant) -> None:
    """A room turned off through the integration stays off after a restart."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(TRV, "heat", {"temperature": 18.0})

    await _entity(hass, HVACMode.OFF)._async_startup_sync_trv()

    assert [c.data for c in set_mode] == [{"entity_id": TRV, "hvac_mode": HVACMode.OFF}]
    assert not set_temp


async def test_startup_sync_leaves_auto_mode_alone(hass: HomeAssistant) -> None:
    """A TRV running its own schedule is not forced into heat."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(TRV, "auto", {"temperature": 21.0})

    await _entity(hass, HVACMode.HEAT)._async_startup_sync_trv()

    assert not set_mode
    assert not set_temp


async def test_startup_sync_turns_off_trv_back_on(hass: HomeAssistant) -> None:
    """A TRV found off while the room should be heating is switched back on."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(TRV, "off", {"temperature": 18.0})

    await _entity(hass, HVACMode.HEAT, target=21.0)._async_startup_sync_trv()

    assert [c.data for c in set_mode] == [{"entity_id": TRV, "hvac_mode": HVACMode.HEAT}]
    assert [c.data["temperature"] for c in set_temp] == [21.0]


async def test_startup_sync_skips_unavailable_trv(hass: HomeAssistant) -> None:
    """Nothing is sent to a TRV that has not come online yet."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(TRV, "unavailable")

    await _entity(hass, HVACMode.HEAT)._async_startup_sync_trv()

    assert not set_mode
    assert not set_temp
