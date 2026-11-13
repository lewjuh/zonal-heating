"""Tests for the zone state machine."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from custom_components.zonal_heating.room_state_machine import RoomStateMachine
from custom_components.zonal_heating.storage import ZonalHeatingStorage
from custom_components.zonal_heating.zone_state_machine import (
    STARTUP_GRACE_PERIOD,
    ZoneStateMachine,
)

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

async def test_zone_in_heat_with_low_target_is_reboosted(hass: HomeAssistant) -> None:
    """A zone already in heat but with a setpoint below its temperature is raised."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(
        ZONE, "heat", {"current_temperature": 20.0, "temperature": 18.0, "max_temp": 35}
    )

    zone = await _make_zone(hass, room_temp=18.0)

    assert not set_mode
    assert set_temp
    assert set_temp[-1].data == {"entity_id": ZONE, "temperature": 25.0}
    await zone.async_stop()

async def test_zone_target_drop_while_heating_triggers_reboost(hass: HomeAssistant) -> None:
    """The zone's own schedule lowering its setpoint mid-demand is undone."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(
        ZONE, "heat", {"current_temperature": 20.0, "temperature": 25.0, "max_temp": 35}
    )
    zone = await _make_zone(hass, room_temp=18.0)
    assert not set_temp

    hass.states.async_set(
        ZONE, "heat", {"current_temperature": 20.0, "temperature": 16.0, "max_temp": 35}
    )
    await hass.async_block_till_done()

    assert set_temp[-1].data == {"entity_id": ZONE, "temperature": 25.0}
    await zone.async_stop()

async def test_zone_in_heat_with_adequate_target_is_left_alone(hass: HomeAssistant) -> None:
    """No calls are made to a zone already heating towards a high enough target."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(
        ZONE, "heat", {"current_temperature": 20.0, "temperature": 22.0, "max_temp": 35}
    )

    zone = await _make_zone(hass, room_temp=18.0)

    assert not set_mode and not set_temp
    await zone.async_stop()


async def _restored_zone(
    hass: HomeAssistant, changed_ago: timedelta, **zone_kwargs
) -> ZoneStateMachine:
    """Build a zone whose last turn-on was restored from storage."""
    storage = ZonalHeatingStorage(hass, "entry")
    await storage.async_load()
    storage.set_zone_state("Upstairs", True, dt_util.now() - changed_ago)
    room = RoomStateMachine(hass, "Bedroom", TRV, [])
    zone = ZoneStateMachine(hass, "Upstairs", ZONE, [room], storage=storage, **zone_kwargs)
    await zone.async_start()
    return zone


async def test_reload_keeps_min_on_time_when_state_restored(hass: HomeAssistant) -> None:
    """A reload does not let a zone that just turned on be switched straight off."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(ZONE, "heat", {"current_temperature": 19.0, "temperature": 24.0})
    hass.states.async_set(TRV, "heat", {"current_temperature": 21.5, "temperature": 21.0})

    zone = await _restored_zone(hass, timedelta(minutes=1), min_on_time=10)

    assert not zone.in_startup_grace_period
    assert not set_mode
    assert zone.retry_timer_active
    await zone.async_stop()


async def test_startup_does_not_turn_zone_off_before_rooms_report(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A heating zone is left on while its TRVs are still unknown after a restart."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(ZONE, "heat", {"current_temperature": 19.0, "temperature": 24.0})
    hass.states.async_set(TRV, "unknown")

    zone = await _restored_zone(hass, timedelta(hours=2), min_on_time=10)
    assert not set_mode
    assert zone.retry_timer_active

    await _set_room_temp(hass, zone, 18.0)
    assert not set_mode
    assert zone.zone_is_on

    # A TRV that never comes back does not hold the zone on for ever
    hass.states.async_set(TRV, "unavailable")
    await zone.rooms[0].async_update_climate_state()
    zone.rooms[0]._state_known = False
    freezer.tick(timedelta(seconds=STARTUP_GRACE_PERIOD + 1))
    await zone._async_evaluate_zone()
    assert set_mode[-1].data == {"entity_id": ZONE, "hvac_mode": "off"}
    await zone.async_stop()


async def test_thermostat_dropout_does_not_reset_min_on_clock(hass: HomeAssistant) -> None:
    """A thermostat going unavailable and back is not treated as off then on."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    heating = {"current_temperature": 19.0, "temperature": 24.0}
    hass.states.async_set(ZONE, "heat", heating)

    zone = await _make_zone(hass, room_temp=18.0)
    changed_at = dt_util.now() - timedelta(minutes=30)
    zone._last_zone_change = changed_at

    hass.states.async_set(ZONE, "unavailable")
    await hass.async_block_till_done()
    assert zone.zone_is_on

    hass.states.async_set(ZONE, "heat", heating)
    await hass.async_block_till_done()
    assert zone.zone_is_on
    assert zone.last_zone_change == changed_at
    await zone.async_stop()


async def test_stop_during_zone_change_leaves_no_timers(hass: HomeAssistant) -> None:
    """Stopping mid-change (a reload) does not leave the old state machine running."""
    release = asyncio.Event()
    calls: list[ServiceCall] = []

    async def slow_service(call: ServiceCall) -> None:
        calls.append(call)
        await release.wait()

    hass.services.async_register("climate", "set_hvac_mode", slow_service)
    hass.services.async_register("climate", "set_temperature", slow_service)
    hass.states.async_set(ZONE, "off", {"current_temperature": 19.0, "max_temp": 35})

    zone = await _make_zone(hass, room_temp=21.5)
    hass.states.async_set(TRV, "heat", {"current_temperature": 18.0, "temperature": 21.0})
    check = hass.async_create_task(zone._async_periodic_check())
    await asyncio.sleep(0)
    while not calls:
        await asyncio.sleep(0)

    await zone.async_stop()
    release.set()
    await check
    await hass.async_block_till_done()

    assert zone._periodic_timer is None
    assert zone._retry_timer is None
    assert zone._eval_debounce_timer is None

    calls.clear()
    zone._on_room_needs_heat_changed()
    await zone._async_evaluate_zone()
    await zone._async_periodic_check()
    assert zone._eval_debounce_timer is None
    assert zone._periodic_timer is None
    assert not calls
