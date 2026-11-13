"""Tests for the virtual climate entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    mock_restore_cache,
)

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant, State

import custom_components.zonal_heating  # noqa: F401 - imported so it can be patched
from custom_components.zonal_heating.climate import ZonalHeatingClimate
from custom_components.zonal_heating.const import DOMAIN

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


VIRTUAL = "climate.zonal_heating_upstairs_bedroom"


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a one-room entry without the real frontend and http components."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "zones": [
                {
                    "name": "Upstairs",
                    "zone_thermostat": "climate.upstairs",
                    "rooms": [{"name": "Bedroom", "trv_entity": TRV}],
                }
            ],
            "settings": {},
        },
    )
    entry.add_to_hass(hass)
    hass.config.components.update({"frontend", "http"})
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    with patch("custom_components.zonal_heating.add_extra_js_url"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_new_room_adopts_trv_instead_of_pushing_defaults(hass: HomeAssistant) -> None:
    """A room with no previous state takes the TRV's target and mode, and writes nothing."""
    hass.states.async_set("climate.upstairs", "off", {"current_temperature": 19.0})
    hass.states.async_set(TRV, "off", {"current_temperature": 18.0, "temperature": 17.0})

    entry = await _setup_entry(hass)

    state = hass.states.get(VIRTUAL)
    assert state.state == HVACMode.OFF
    assert state.attributes["temperature"] == 17.0
    entity = hass.data["climate"].get_entity(VIRTUAL)
    assert entity._startup_sync_timer is None, "defaults must not be pushed to the TRV"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_restored_room_still_pushes_its_target(hass: HomeAssistant) -> None:
    """A room with a restored target keeps it and schedules the startup sync."""
    mock_restore_cache(hass, [State(VIRTUAL, "heat", {"temperature": 21.0})])
    hass.states.async_set("climate.upstairs", "off", {"current_temperature": 19.0})
    hass.states.async_set(TRV, "off", {"current_temperature": 18.0, "temperature": 17.0})

    entry = await _setup_entry(hass)

    state = hass.states.get(VIRTUAL)
    assert state.state == HVACMode.HEAT
    assert state.attributes["temperature"] == 21.0
    entity = hass.data["climate"].get_entity(VIRTUAL)
    assert entity._startup_sync_timer is not None
    await hass.config_entries.async_unload(entry.entry_id)
