"""Config flow for zonal_heating integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.person import DOMAIN as PERSON_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AWAY_MODE_DELAY,
    CONF_AWAY_TEMPERATURE,
    CONF_MIN_CYCLE_TIME,
    CONF_OVERHEAT_THRESHOLD,
    CONF_PERSON_ENTITIES,
    CONF_PRIORITY,
    CONF_ROOMS,
    CONF_SETTINGS,
    CONF_TEMP_DIFFERENTIAL,
    CONF_TRV_ENTITY,
    CONF_WINDOW_DELAY,
    CONF_WINDOW_SENSORS,
    CONF_ZONE_NAME,
    CONF_ZONE_THERMOSTAT,
    CONF_ZONES,
    DEFAULT_AWAY_MODE_DELAY,
    DEFAULT_AWAY_TEMPERATURE,
    DEFAULT_MIN_CYCLE_TIME,
    DEFAULT_OVERHEAT_THRESHOLD,
    DEFAULT_PRIORITY,
    DEFAULT_TEMP_DIFFERENTIAL,
    DEFAULT_WINDOW_DELAY,
    DOMAIN,
    PRIORITY_MAX,
    PRIORITY_MIN,
)

_LOGGER = logging.getLogger(__name__)


class ZonalHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for zonal_heating."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ZonalHeatingOptionsFlow:
        """Get the options flow for this handler."""
        return ZonalHeatingOptionsFlow()

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._zones: list[dict[str, Any]] = []
        self._current_zone: dict[str, Any] = {}
        self._current_rooms: list[dict[str, Any]] = []
        self._title: str = ""
        self._reconfigure_zone_index: int | None = None
        self._reconfigure_room_index: int | None = None
        self._reconfigure_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - go directly to adding zones."""
        # Set default title and skip directly to zone setup
        self._title = "Zonal Heating"
        return await self.async_step_add_zone()

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a zone with its thermostat."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate zone thermostat is a climate entity
            zone_thermostat = user_input[CONF_ZONE_THERMOSTAT]
            if not self.hass.states.get(zone_thermostat):
                errors["base"] = "invalid_thermostat"
            elif zone_thermostat in [z[CONF_ZONE_THERMOSTAT] for z in self._zones]:
                errors["base"] = "duplicate_zone_thermostat"
            else:
                self._current_zone = {
                    CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                    CONF_ZONE_THERMOSTAT: zone_thermostat,
                }
                self._current_rooms = []
                return await self.async_step_add_room()

        return self.async_show_form(
            step_id="add_zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_NAME): str,
                    vol.Required(CONF_ZONE_THERMOSTAT): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a room to the current zone."""
        errors: dict[str, str] = {}

        if user_input is not None:
            trv_entity = user_input[CONF_TRV_ENTITY]

            # Validate TRV entity exists
            if not self.hass.states.get(trv_entity):
                errors["base"] = "invalid_trv"
            # Check if TRV already used in current zone
            elif trv_entity in [r[CONF_TRV_ENTITY] for r in self._current_rooms]:
                errors["base"] = "duplicate_trv"
            else:
                # Add room to current zone
                room = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_TRV_ENTITY: trv_entity,
                    CONF_WINDOW_SENSORS: user_input.get(CONF_WINDOW_SENSORS, []),
                    CONF_PRIORITY: user_input.get(CONF_PRIORITY, DEFAULT_PRIORITY),
                }
                self._current_rooms.append(room)

                # Ask if user wants to add another room or finish zone
                return await self.async_step_zone_complete()

        return self.async_show_form(
            step_id="add_room",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_TRV_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
                    ),
                    vol.Optional(CONF_WINDOW_SENSORS): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=BINARY_SENSOR_DOMAIN,
                            device_class="window",
                            multiple=True,
                        )
                    ),
                    vol.Optional(CONF_PRIORITY, default=DEFAULT_PRIORITY): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=PRIORITY_MIN, max=PRIORITY_MAX),
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "zone_name": self._current_zone[CONF_ZONE_NAME],
                "room_count": str(len(self._current_rooms)),
            },
        )

    async def async_step_zone_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask if user wants to add another room or finish the zone."""
        if user_input is not None:
            if user_input.get("add_another_room"):
                return await self.async_step_add_room()

            # Finish current zone
            self._current_zone[CONF_ROOMS] = self._current_rooms
            self._zones.append(self._current_zone)

            # Ask if user wants to add another zone
            return await self.async_step_zones_complete()

        return self.async_show_form(
            step_id="zone_complete",
            data_schema=vol.Schema(
                {
                    vol.Required("add_another_room", default=False): bool,
                }
            ),
            description_placeholders={
                "zone_name": self._current_zone[CONF_ZONE_NAME],
                "room_count": str(len(self._current_rooms)),
            },
        )

    async def async_step_zones_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask if user wants to add another zone or continue to settings."""
        if user_input is not None:
            if user_input.get("add_another_zone"):
                return await self.async_step_add_zone()

            # Continue to global settings
            return await self.async_step_settings()

        return self.async_show_form(
            step_id="zones_complete",
            data_schema=vol.Schema(
                {
                    vol.Required("add_another_zone", default=False): bool,
                }
            ),
            description_placeholders={
                "zone_count": str(len(self._zones)),
            },
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure global settings."""
        if user_input is not None:
            # Create the config entry
            config_data = {
                CONF_ZONES: self._zones,
                CONF_SETTINGS: {
                    CONF_TEMP_DIFFERENTIAL: user_input[CONF_TEMP_DIFFERENTIAL],
                    CONF_OVERHEAT_THRESHOLD: user_input[CONF_OVERHEAT_THRESHOLD],
                    CONF_MIN_CYCLE_TIME: user_input[CONF_MIN_CYCLE_TIME],
                    CONF_WINDOW_DELAY: user_input[CONF_WINDOW_DELAY],
                    CONF_PERSON_ENTITIES: user_input.get(CONF_PERSON_ENTITIES, []),
                    CONF_AWAY_TEMPERATURE: user_input[CONF_AWAY_TEMPERATURE],
                    CONF_AWAY_MODE_DELAY: user_input[CONF_AWAY_MODE_DELAY],
                },
            }

            return self.async_create_entry(
                title=self._title,
                data=config_data,
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TEMP_DIFFERENTIAL,
                        default=DEFAULT_TEMP_DIFFERENTIAL,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5.0)),
                    vol.Optional(
                        CONF_OVERHEAT_THRESHOLD,
                        default=DEFAULT_OVERHEAT_THRESHOLD,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=5.0)),
                    vol.Optional(
                        CONF_MIN_CYCLE_TIME,
                        default=DEFAULT_MIN_CYCLE_TIME,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Optional(
                        CONF_WINDOW_DELAY,
                        default=DEFAULT_WINDOW_DELAY,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                    vol.Optional(CONF_PERSON_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=PERSON_DOMAIN,
                            multiple=True,
                        )
                    ),
                    vol.Optional(
                        CONF_AWAY_TEMPERATURE,
                        default=DEFAULT_AWAY_TEMPERATURE,
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=25.0)),
                    vol.Optional(
                        CONF_AWAY_MODE_DELAY,
                        default=DEFAULT_AWAY_MODE_DELAY,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration - select which zone to edit."""
        # Get the config entry being reconfigured
        self._reconfigure_entry = self._get_reconfigure_entry()

        # Load existing zones
        self._zones = self._reconfigure_entry.data.get(CONF_ZONES, [])

        if not self._zones:
            return self.async_abort(reason="no_zones")

        if user_input is not None:
            zone_idx = user_input["zone_to_edit"]
            self._reconfigure_zone_index = zone_idx
            self._current_zone = self._zones[zone_idx].copy()
            self._current_rooms = self._current_zone.get(CONF_ROOMS, []).copy()
            return await self.async_step_reconfigure_zone()

        # Build zone selection options
        zone_options = {
            idx: f"{zone.get(CONF_ZONE_NAME, f'Zone {idx}')} ({zone.get(CONF_ZONE_THERMOSTAT)})"
            for idx, zone in enumerate(self._zones)
        }

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("zone_to_edit"): vol.In(zone_options),
                }
            ),
            description_placeholders={
                "zone_count": str(len(self._zones)),
            },
        )

    async def async_step_reconfigure_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit zone details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            zone_thermostat = user_input[CONF_ZONE_THERMOSTAT]

            # Validate zone thermostat exists
            if not self.hass.states.get(zone_thermostat):
                errors["base"] = "invalid_thermostat"
            # Check if thermostat is used by another zone
            elif any(
                idx != self._reconfigure_zone_index
                and z[CONF_ZONE_THERMOSTAT] == zone_thermostat
                for idx, z in enumerate(self._zones)
            ):
                errors["base"] = "duplicate_zone_thermostat"
            else:
                # Update zone details
                self._current_zone[CONF_ZONE_NAME] = user_input[CONF_ZONE_NAME]
                self._current_zone[CONF_ZONE_THERMOSTAT] = zone_thermostat
                return await self.async_step_reconfigure_zone_menu()

        # Pre-fill with current values
        return self.async_show_form(
            step_id="reconfigure_zone",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ZONE_NAME,
                        default=self._current_zone.get(CONF_ZONE_NAME, ""),
                    ): str,
                    vol.Required(
                        CONF_ZONE_THERMOSTAT,
                        default=self._current_zone.get(CONF_ZONE_THERMOSTAT),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_zone_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show menu for zone actions."""
        if user_input is not None:
            action = user_input.get("action")

            if action == "add_room":
                self._reconfigure_room_index = None
                return await self.async_step_reconfigure_room()
            if action == "edit_room":
                return await self.async_step_select_room_to_edit()
            if action == "delete_room":
                return await self.async_step_select_room_to_delete()
            if action == "save":
                # Save changes
                self._current_zone[CONF_ROOMS] = self._current_rooms
                self._zones[self._reconfigure_zone_index] = self._current_zone

                # Update config entry
                new_data = self._reconfigure_entry.data.copy()
                new_data[CONF_ZONES] = self._zones

                return self.async_update_reload_and_abort(
                    self._reconfigure_entry,
                    data=new_data,
                    reason="reconfigure_successful",
                )

        menu_options = ["add_room", "save"]
        if self._current_rooms:
            menu_options.insert(1, "edit_room")
            menu_options.insert(2, "delete_room")

        return self.async_show_form(
            step_id="reconfigure_zone_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): vol.In(
                        {
                            "add_room": "Add a room",
                            "edit_room": "Edit a room",
                            "delete_room": "Delete a room",
                            "save": "Save changes and finish",
                        }
                    ),
                }
            ),
            description_placeholders={
                "zone_name": self._current_zone[CONF_ZONE_NAME],
                "room_count": str(len(self._current_rooms)),
            },
        )

    async def async_step_select_room_to_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which room to edit."""
        if user_input is not None:
            self._reconfigure_room_index = user_input["room_to_edit"]
            return await self.async_step_reconfigure_room()

        room_options = {
            idx: f"{room.get(CONF_NAME, f'Room {idx}')} ({room.get(CONF_TRV_ENTITY)})"
            for idx, room in enumerate(self._current_rooms)
        }

        return self.async_show_form(
            step_id="select_room_to_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("room_to_edit"): vol.In(room_options),
                }
            ),
        )

    async def async_step_select_room_to_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which room to delete."""
        if user_input is not None:
            room_to_delete = user_input["room_to_delete"]
            del self._current_rooms[room_to_delete]
            return await self.async_step_reconfigure_zone_menu()

        room_options = {
            idx: f"{room.get(CONF_NAME, f'Room {idx}')} ({room.get(CONF_TRV_ENTITY)})"
            for idx, room in enumerate(self._current_rooms)
        }

        return self.async_show_form(
            step_id="select_room_to_delete",
            data_schema=vol.Schema(
                {
                    vol.Required("room_to_delete"): vol.In(room_options),
                }
            ),
        )

    async def async_step_reconfigure_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a room."""
        errors: dict[str, str] = {}

        if user_input is not None:
            trv_entity = user_input[CONF_TRV_ENTITY]

            # Validate TRV entity exists
            if not self.hass.states.get(trv_entity):
                errors["base"] = "invalid_trv"
            # Check if TRV already used in another room (excluding current room if editing)
            elif any(
                idx != self._reconfigure_room_index and r[CONF_TRV_ENTITY] == trv_entity
                for idx, r in enumerate(self._current_rooms)
            ):
                errors["base"] = "duplicate_trv"
            else:
                room = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_TRV_ENTITY: trv_entity,
                    CONF_WINDOW_SENSORS: user_input.get(CONF_WINDOW_SENSORS, []),
                    CONF_PRIORITY: user_input.get(CONF_PRIORITY, DEFAULT_PRIORITY),
                }

                if self._reconfigure_room_index is not None:
                    # Edit existing room
                    self._current_rooms[self._reconfigure_room_index] = room
                else:
                    # Add new room
                    self._current_rooms.append(room)

                return await self.async_step_reconfigure_zone_menu()

        # Get current values if editing
        current_room = (
            self._current_rooms[self._reconfigure_room_index]
            if self._reconfigure_room_index is not None
            else {}
        )

        return self.async_show_form(
            step_id="reconfigure_room",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=current_room.get(CONF_NAME, "")
                    ): str,
                    vol.Required(
                        CONF_TRV_ENTITY, default=current_room.get(CONF_TRV_ENTITY)
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
                    ),
                    vol.Optional(
                        CONF_WINDOW_SENSORS,
                        default=current_room.get(CONF_WINDOW_SENSORS, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=BINARY_SENSOR_DOMAIN,
                            device_class="window",
                            multiple=True,
                        )
                    ),
                    vol.Optional(
                        CONF_PRIORITY,
                        default=current_room.get(CONF_PRIORITY, DEFAULT_PRIORITY),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=PRIORITY_MIN, max=PRIORITY_MAX),
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "zone_name": self._current_zone[CONF_ZONE_NAME],
            },
        )


class ZonalHeatingOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for zonal heating integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Save settings to options
            return self.async_create_entry(
                title="",
                data={
                    CONF_TEMP_DIFFERENTIAL: user_input[CONF_TEMP_DIFFERENTIAL],
                    CONF_OVERHEAT_THRESHOLD: user_input[CONF_OVERHEAT_THRESHOLD],
                    CONF_MIN_CYCLE_TIME: user_input[CONF_MIN_CYCLE_TIME],
                    CONF_WINDOW_DELAY: user_input[CONF_WINDOW_DELAY],
                    CONF_PERSON_ENTITIES: user_input.get(CONF_PERSON_ENTITIES, []),
                    CONF_AWAY_TEMPERATURE: user_input[CONF_AWAY_TEMPERATURE],
                    CONF_AWAY_MODE_DELAY: user_input[CONF_AWAY_MODE_DELAY],
                },
            )

        # Get current settings from options (fallback to data for backwards compatibility)
        current_settings = (
            self.config_entry.options
            if self.config_entry.options
            else self.config_entry.data.get(CONF_SETTINGS, {})
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TEMP_DIFFERENTIAL,
                        default=current_settings.get(
                            CONF_TEMP_DIFFERENTIAL, DEFAULT_TEMP_DIFFERENTIAL
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5.0)),
                    vol.Optional(
                        CONF_OVERHEAT_THRESHOLD,
                        default=current_settings.get(
                            CONF_OVERHEAT_THRESHOLD, DEFAULT_OVERHEAT_THRESHOLD
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=5.0)),
                    vol.Optional(
                        CONF_MIN_CYCLE_TIME,
                        default=current_settings.get(
                            CONF_MIN_CYCLE_TIME, DEFAULT_MIN_CYCLE_TIME
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Optional(
                        CONF_WINDOW_DELAY,
                        default=current_settings.get(
                            CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                    vol.Optional(
                        CONF_PERSON_ENTITIES,
                        default=current_settings.get(CONF_PERSON_ENTITIES, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=PERSON_DOMAIN,
                            multiple=True,
                        )
                    ),
                    vol.Optional(
                        CONF_AWAY_TEMPERATURE,
                        default=current_settings.get(
                            CONF_AWAY_TEMPERATURE, DEFAULT_AWAY_TEMPERATURE
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=25.0)),
                    vol.Optional(
                        CONF_AWAY_MODE_DELAY,
                        default=current_settings.get(
                            CONF_AWAY_MODE_DELAY, DEFAULT_AWAY_MODE_DELAY
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                }
            ),
        )
