"""Room scheduler for zonal heating integration."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from collections.abc import Callable

    from .room_state_machine import RoomStateMachine
    from .storage import ZonalHeatingStorage

_LOGGER = logging.getLogger(__name__)


class RoomScheduler:
    """Scheduler for a single room's temperature schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        room_name: str,
        room_state_machine: "RoomStateMachine",
        storage: "ZonalHeatingStorage",
    ) -> None:
        """Initialise the room scheduler."""
        self.hass = hass
        self.room_name = room_name
        self._room_sm = room_state_machine
        self._storage = storage

        self._schedule_enabled = False
        self._weekday_schedule: list[dict] = []
        self._weekend_schedule: list[dict] = []

        self._last_scheduled_temp: float | None = None
        self._last_applied_time: str | None = None
        self._manual_override_active = False
        self._queued_temperature: float | None = None

        self._unsub_minute_check: Callable | None = None

    async def async_start(self) -> None:
        """Start the scheduler."""
        await self.async_reload_schedule()

        self._unsub_minute_check = async_track_time_change(
            self.hass,
            self._async_minute_check,
            second=0,
        )
        _LOGGER.debug("%s: Scheduler started", self.room_name)

    async def async_stop(self) -> None:
        """Stop the scheduler."""
        if self._unsub_minute_check:
            self._unsub_minute_check()
            self._unsub_minute_check = None
        _LOGGER.debug("%s: Scheduler stopped", self.room_name)

    async def async_reload_schedule(self) -> None:
        """Reload schedule from storage."""
        schedule = self._storage.get_room_schedule(self.room_name)
        if schedule:
            self._schedule_enabled = schedule.get("enabled", True)
            self._weekday_schedule = schedule.get("weekday", [])
            self._weekend_schedule = schedule.get("weekend", [])
            _LOGGER.info(
                "%s: Loaded schedule (enabled=%s, weekday=%d, weekend=%d)",
                self.room_name,
                self._schedule_enabled,
                len(self._weekday_schedule),
                len(self._weekend_schedule),
            )
        else:
            self._schedule_enabled = False
            self._weekday_schedule = []
            self._weekend_schedule = []

    @property
    def schedule_enabled(self) -> bool:
        """Return whether the schedule is enabled."""
        return self._schedule_enabled

    @property
    def manual_override_active(self) -> bool:
        """Return whether a manual override is active."""
        return self._manual_override_active

    @property
    def queued_temperature(self) -> float | None:
        """Return the queued temperature if any."""
        return self._queued_temperature

    @callback
    def _async_minute_check(self, now: datetime) -> None:
        """Check if a scheduled temperature change should occur."""
        self.hass.async_create_task(self._async_do_minute_check(now))

    async def _async_do_minute_check(self, now: datetime) -> None:
        """Perform the minute check."""
        if not self._schedule_enabled:
            return

        is_weekend = now.weekday() >= 5
        schedule = self._weekend_schedule if is_weekend else self._weekday_schedule

        if not schedule:
            return

        current_time = now.strftime("%H:%M")
        scheduled_temp = self._get_scheduled_temp_at_time(schedule, current_time)

        if scheduled_temp is None:
            return

        is_exact_match = any(p["time"] == current_time for p in schedule)

        if is_exact_match and current_time != self._last_applied_time:
            self._manual_override_active = False
            self._last_applied_time = current_time
            await self._async_apply_scheduled_temperature(scheduled_temp)
        elif self._last_scheduled_temp != scheduled_temp and not self._manual_override_active:
            self._last_scheduled_temp = scheduled_temp

    def _get_scheduled_temp_at_time(
        self, schedule: list[dict], current_time: str
    ) -> float | None:
        """Get the scheduled temperature for the current time."""
        if not schedule:
            return None

        active_temp = None

        for point in schedule:
            if point["time"] <= current_time:
                active_temp = point["temperature"]
            else:
                break

        if active_temp is None:
            active_temp = schedule[-1]["temperature"]

        return active_temp

    async def _async_apply_scheduled_temperature(self, temperature: float) -> None:
        """Apply a scheduled temperature, or queue it if conditions block."""
        if self._room_sm._window_open_confirmed or self._room_sm._overheated:
            self._queued_temperature = temperature
            _LOGGER.info(
                "%s: Scheduled temp %.1fC queued - waiting for condition to clear",
                self.room_name,
                temperature,
            )
            return

        await self._room_sm._async_set_trv_target_temp(temperature)
        self._last_scheduled_temp = temperature
        _LOGGER.info(
            "%s: Applied scheduled temperature: %.1fC",
            self.room_name,
            temperature,
        )

    async def async_check_queued_temperature(self) -> None:
        """Check and apply queued temperature when conditions clear."""
        if self._queued_temperature is None:
            return

        if self._room_sm._window_open_confirmed or self._room_sm._overheated:
            return

        temp = self._queued_temperature
        self._queued_temperature = None

        await self._room_sm._async_set_trv_target_temp(temp)
        self._last_scheduled_temp = temp
        _LOGGER.info(
            "%s: Applied queued scheduled temperature: %.1fC",
            self.room_name,
            temp,
        )

    def handle_manual_override(self, temperature: float) -> None:
        """Mark that a manual override has occurred."""
        if not self._schedule_enabled:
            return

        self._manual_override_active = True
        _LOGGER.info(
            "%s: Manual override to %.1fC - will resume at next schedule point",
            self.room_name,
            temperature,
        )

    def get_current_scheduled_temp(self) -> float | None:
        """Get the currently scheduled temperature."""
        if not self._schedule_enabled:
            return None

        now = dt_util.now()
        is_weekend = now.weekday() >= 5
        schedule = self._weekend_schedule if is_weekend else self._weekday_schedule

        if not schedule:
            return None

        current_time = now.strftime("%H:%M")
        return self._get_scheduled_temp_at_time(schedule, current_time)

    def get_next_schedule_point(self) -> tuple[str, float] | None:
        """Get the next schedule point time and temperature."""
        if not self._schedule_enabled:
            return None

        now = dt_util.now()
        current_time = now.strftime("%H:%M")
        is_weekend = now.weekday() >= 5
        schedule = self._weekend_schedule if is_weekend else self._weekday_schedule

        if not schedule:
            return None

        for point in schedule:
            if point["time"] > current_time:
                return (point["time"], point["temperature"])

        if schedule:
            return (schedule[0]["time"], schedule[0]["temperature"])

        return None
