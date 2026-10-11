"""Tests for the room state machine."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant

from custom_components.zonal_heating.room_state_machine import RoomStateMachine
from custom_components.zonal_heating.storage import ZonalHeatingStorage

TRV = "climate.bedroom_trv"
WINDOW = "binary_sensor.bedroom_window"


def _set_trv(hass: HomeAssistant, current: float, target: float = 21.0, mode: str = "heat") -> None:
    hass.states.async_set(
        TRV, mode, {"current_temperature": current, "temperature": target}
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
