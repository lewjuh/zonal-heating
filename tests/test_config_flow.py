"""Tests for the config flow."""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.zonal_heating.const import DOMAIN
from custom_components.zonal_heating.sensor import _async_migrate_zone_unique_ids

ENTRY_DATA = {
    "zones": [
        {
            "name": "Upstairs",
            "zone_thermostat": "climate.upstairs",
            "rooms": [
                {
                    "name": "Bedroom",
                    "trv_entity": "climate.bedroom_trv",
                    "temp_sensor": None,
                    "window_sensors": [],
                    "priority": 5,
                }
            ],
        }
    ],
    "settings": {
        "temp_differential": 0.25,
        "min_on_time": 10,
        "min_off_time": 10,
        "window_delay": 30,
        "calibration_sync": False,
    },
}


@pytest.fixture(autouse=True)
def _entities(hass: HomeAssistant) -> None:
    hass.config.components.update({"http", "frontend"})
    for entity_id in (
        "climate.upstairs",
        "climate.downstairs",
        "climate.bedroom_trv",
        "climate.study_trv",
        "climate.kitchen_trv",
    ):
        hass.states.async_set(entity_id, "heat")


@pytest.fixture(autouse=True)
def _no_setup():
    with patch(
        "custom_components.zonal_heating.async_setup_entry", return_value=True
    ), patch(
        "custom_components.zonal_heating.async_unload_entry", return_value=True
    ):
        yield


async def _start_user_flow_with_one_zone(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Upstairs", "zone_thermostat": "climate.upstairs"}
    )
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Bedroom", "trv_entity": "climate.bedroom_trv"}
    )
    await hass.config_entries.flow.async_configure(flow_id, {"add_another_room": False})
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"add_another_zone": True}
    )
    assert result["step_id"] == "add_zone"
    return flow_id


async def test_duplicate_zone_name_rejected(hass: HomeAssistant) -> None:
    """Zone names must be unique, ignoring case and spaces vs underscores."""
    flow_id = await _start_user_flow_with_one_zone(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {"name": "upstairs", "zone_thermostat": "climate.downstairs"}
    )

    assert result["errors"] == {"base": "duplicate_zone_name"}


async def test_trv_reused_in_another_zone_rejected(hass: HomeAssistant) -> None:
    """A TRV can only belong to one room across all zones."""
    flow_id = await _start_user_flow_with_one_zone(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Downstairs", "zone_thermostat": "climate.downstairs"}
    )

    result = await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Kitchen", "trv_entity": "climate.bedroom_trv"}
    )

    assert result["errors"] == {"base": "duplicate_trv"}


async def test_room_name_slug_clash_rejected(hass: HomeAssistant) -> None:
    """Room names that would produce the same entity IDs are rejected."""
    flow_id = await _start_user_flow_with_one_zone(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Downstairs", "zone_thermostat": "climate.downstairs"}
    )

    result = await hass.config_entries.flow.async_configure(
        flow_id, {"name": "bedroom", "trv_entity": "climate.kitchen_trv"}
    )

    assert result["errors"] == {"base": "duplicate_room_name"}


async def test_thermostat_used_by_other_entry_rejected(hass: HomeAssistant) -> None:
    """A second config entry cannot drive a thermostat the first already controls."""
    MockConfigEntry(domain=DOMAIN, data=copy.deepcopy(ENTRY_DATA)).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Other", "zone_thermostat": "climate.upstairs"}
    )

    assert result["errors"] == {"base": "duplicate_zone_thermostat"}


async def test_reconfigure_saves_changes(hass: HomeAssistant) -> None:
    """Reconfigure edits replace the entry data instead of mutating it in place."""
    entry = MockConfigEntry(domain=DOMAIN, data=copy.deepcopy(ENTRY_DATA))
    entry.add_to_hass(hass)
    original_zones = entry.data["zones"]
    snapshot = copy.deepcopy(original_zones)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(flow_id, {"zone_to_edit": 0})
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Upstairs", "zone_thermostat": "climate.upstairs"}
    )
    await hass.config_entries.flow.async_configure(flow_id, {"action": "edit_room"})
    await hass.config_entries.flow.async_configure(flow_id, {"room_to_edit": 0})
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Main Bedroom", "trv_entity": "climate.bedroom_trv"}
    )
    result = await hass.config_entries.flow.async_configure(flow_id, {"action": "save"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert original_zones == snapshot, "existing entry data was mutated in place"
    assert entry.data["zones"][0]["rooms"][0]["name"] == "Main Bedroom"


async def test_zone_sensor_unique_id_migrated(hass: HomeAssistant) -> None:
    """Zone status sensors move to a unique ID that cannot clash with room sensors."""
    entry = MockConfigEntry(domain=DOMAIN, data=copy.deepcopy(ENTRY_DATA))
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_upstairs_diagnostic", config_entry=entry
    )

    _async_migrate_zone_unique_ids(hass, entry, entry.data["zones"])

    migrated = registry.async_get(old.entity_id)
    assert migrated.unique_id == f"{entry.entry_id}_zone_upstairs_diagnostic"
