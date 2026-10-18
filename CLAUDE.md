# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for intelligent multi-zone heating control. It coordinates zone thermostats with individual room TRVs (thermostatic radiator valves) using a dual state machine architecture.

The core principle is **"set and hold"**: the user sets a temperature on a room, and the system holds it indefinitely. No system ever changes the user's chosen TRV target temperature behind their back.

## Architecture

### State Machine Pattern

The integration uses a **two-level state machine hierarchy**:

1. **Zone State Machine** (`zone_state_machine.py`)
   - Manages zone-level heating decisions
   - Monitors all rooms in a zone
   - Controls the zone thermostat (boiler/heating system)
   - Enforces separate minimum on and off times to prevent boiler short-cycling
   - Coordinates heating based on room priorities and demands

2. **Room State Machine** (`room_state_machine.py`)
   - Manages individual room heating logic
   - Monitors TRV temperature and state
   - Handles window sensor integration with configurable delay
   - Calculates heating need based on temperature differential
   - Optional calibration sync (external temp sensor -> TRV calibration offset)
   - Reports heating demand to zone coordinator

### Component Interaction Flow

```
ConfigFlow -> __init__.py -> Climate Entities (UI layer)
                |
         Zone State Machine (coordinator)
                |
         Room State Machines (workers)
                |
         TRV Entities (hardware)
```

### Temperature Write Points

Only **4 paths** write to TRVs:

1. **User sets temperature** via virtual entity -> forwards to TRV (`climate.py`)
2. **Startup sync** pushes restored target and on/off mode to TRV; a TRV in `auto` or another active mode is not forced to `heat` (`climate.py`)
3. **Calibration sync** writes external temp/offset to TRV number entity (`room_state_machine.py`) - not a target temp write. Sync entities are discovered from the entity registry, never from current states: Z2M entities are `unknown` for ~45 s after HA starts, and state-based discovery silently disabled calibration in 1.8.x. Sonoff TRVZB's external temperature input and sensor selector stay `unknown` until written, so sync writes them regardless (selector option `remote_temperature`); waiting for them to become known left calibration dead in 1.9.0. If the TRV has not adopted the external temperature 10 min after the first write (selector not reporting the remote option, or, without a selector, its reading not matching), sync falls back to the calibration offset: some TRVZB firmware ignores the remote sensor
4. **Zone thermostat** gets set to heat at current+5, capped at its `max_temp`, when turning on; a zone already in `heat` whose setpoint is less than 1C above its current temperature (its own schedule or a manual change) is re-boosted the same way (`zone_state_machine.py`)

### Key Design Decisions

1. **Climate Entities are Virtual**: The `ZonalHeatingClimate` entities in `climate.py` are virtual UI wrappers that forward commands to actual TRVs while displaying coordinated state.

2. **State Machines are Coordinators**: The zone/room state machines (`zone_state_machine.py`, `room_state_machine.py`) are the actual control logic, created in `__init__.py` after entities are set up.

3. **Event-Driven Updates**: Both state machines use `async_track_state_change_event` to react to entity changes rather than polling.

4. **Minimum On/Off Time Protection**: The zone stays on for at least `min_on_time` after turning on and off for at least `min_off_time` after turning off. When blocked, it automatically schedules a retry.

5. **Window Detection Suppresses Demand Only**: When a window opens (after configurable delay), the room's `needs_heat` flag is suppressed so the zone won't call for heat. The TRV target temperature is never changed.

6. **Target Set Suppression**: After the user changes temperature via the virtual entity, TRV-to-virtual sync is suppressed for 5 seconds (`_target_set_at`) to prevent the old TRV state from overwriting the new target before the TRV has processed it.

## Development Commands

### Installation & Testing in Home Assistant

```bash
# Copy to Home Assistant for testing
cp -r custom_components/zonal_heating /path/to/homeassistant/custom_components/

# Watch logs in real-time
tail -f /path/to/homeassistant/home-assistant.log | grep zonal_heating

# Enable debug logging in configuration.yaml
logger:
  default: info
  logs:
    custom_components.zonal_heating: debug
```

### Tests

```bash
pip install -r requirements_test.txt
pytest -q
```

Tests use `pytest-homeassistant-custom-component` and run in CI (`.github/workflows/validate.yaml`).

### HACS Validation

```bash
# Validate HACS requirements locally (requires HACS action)
# The integration must pass all HACS validation checks in CI/CD
```

**Critical HACS Requirements**:
- `manifest.json` must include: `version`, `issue_tracker`, `documentation`
- GitHub repo must have: description, topics (including `hacs`, `home-assistant`)
- Minimum Home Assistant version: 2024.11.0 (specified in `hacs.json`; needed for `_get_reconfigure_entry` and the argument-less `OptionsFlow`)

### Git Workflow

```bash
# Standard development workflow
git checkout -b feature/your-feature-name
# Make changes
git add .
git commit -m "feat: descriptive message"
git push origin feature/your-feature-name

# After merge to main, users update via HACS
```

## File Structure

```
custom_components/zonal_heating/
├── manifest.json          # MUST have version, issue_tracker, documentation
├── __init__.py            # Entry point: setup, coordinator creation
├── config_flow.py         # Multi-step UI configuration flow
├── climate.py             # Virtual climate entities (UI layer)
├── const.py               # Constants, defaults, attributes
├── room_state_machine.py  # Room-level control logic
├── zone_state_machine.py  # Zone-level coordination logic
├── sensor.py              # Diagnostic sensors (zone/room status)
├── storage.py             # Persistent state storage with migration
├── strings.json           # UI text (primary source)
└── translations/
    └── en.json            # Translated UI text (fallback)
```

## Configuration Flow Architecture

The `config_flow.py` implements a **multi-step wizard**:

1. `async_step_user` -> `async_step_add_zone` (add zones)
2. `async_step_add_room` (add rooms to current zone, repeatable)
3. `async_step_zone_complete` (add more rooms or finish zone)
4. `async_step_zones_complete` (add more zones or continue)
5. `async_step_settings` (global settings, creates entry)

**Settings**: temp_differential, min_on_time, min_off_time, window_delay, calibration_sync

**Reconfiguration Support**: `async_step_reconfigure` allows editing existing zones/rooms without recreating the entire config entry.

## State Tracking & Attributes

### Room State Machine Properties
- `needs_heat`: Latched with hysteresis. Starts when current_temp < target_temp - differential, holds until current_temp >= target_temp. Always false when the climate is off, the TRV is unavailable, or a window is confirmed open
- `trv_satisfied`: The TRV's own view. `hvac_action == idle` when the TRV reports it (Sonoff TRVZB), otherwise TRV reading >= TRV target (Tuya TV02 has no hvac_action)
- `demand_stalled`: Set when the room gains less than 0.2C in 60 min of zone-on time; cleared after 2h, when demand ends, or when the target changes
- `calls_for_heat`: What the zone actually uses: `needs_heat` and deficit > 0 and not `trv_satisfied` and not `demand_stalled`. This stops the boiler running while every valve is shut (seen live: 21 h overnight with the Kitchen TRV reading 1.5C above its room sensor)
- `temperature_deficit`: Used for sorting rooms in logs and diagnostics by the zone coordinator
- `window_open_confirmed`: Only true after delay timer expires

### Zone State Machine Logic
- Evaluates on any room climate state change
- Turns zone ON if any room `calls_for_heat`
- Respects `min_on_time` / `min_off_time` and schedules automatic retry when blocked
- Turns on with `climate.set_hvac_mode: heat` followed by `climate.set_temperature` at `current + 5C` capped at `max_temp`. Never fold `hvac_mode` into the `set_temperature` call: HA passes it through to the integration, and some ignore it (meross_lan MTS200/215 does), which left the zone thermostats stuck off in 1.8.x
- Any mode other than `off` counts as on when deciding whether to turn the zone off

## Common Issues & Solutions

### Integration Not Appearing After HACS Install
**Problem**: `manifest.json` missing required keys or not pushed to GitHub
**Solution**: Ensure `version`, `issue_tracker`, `documentation` are in manifest and pushed to main branch. Users must "Redownload" in HACS after changes.

### Heating Not Activating
**Debug**: Check logs for "ZONE EVALUATION" entries. Verify:
1. At least one room reports `calls_for_heat = True` (not just `needs_heat`; check `trv_satisfied` and `demand_stalled`)
2. Zone not held by `min_on_time` / `min_off_time` (look for "MIN ON TIME" / "MIN OFF TIME BLOCKING")

### Window Sensors Not Working
**Debug**: Check for "Window opened" log entries. The delay (default 30s) prevents false triggers. When confirmed open, the room suppresses its `needs_heat` flag but the TRV target temperature remains unchanged.

## Logging Strategy

The code uses **structured, searchable log messages**:
- `_LOGGER.info()` for state changes and decisions
- `_LOGGER.debug()` for detailed reasoning

When debugging, search logs for:
- `"ZONE EVALUATION"` - zone decision points
- `"MIN ON TIME"` / `"MIN OFF TIME"` - cycling protection
- `"Not warming"` - stall guard dropped a room's demand
- `"ZONE TARGET TOO LOW"` - zone was in heat but its setpoint was too low to fire, so it was raised
- `"ZONE TARGET TOO LOW"` - zone was in heat but its setpoint was too low to fire, so it was raised
- `"Window opened"` - window detection
- `"NEEDS HEAT"` - room heating decisions

## Version Management

**IMPORTANT**: The `version` field in `manifest.json` must be updated for each release. HACS and Home Assistant 2021.6+ require this field. Use semantic versioning (e.g., `1.0.0`, `1.1.0`, `1.1.1`).

When making releases:
1. Update `version` in `manifest.json`
2. Commit and tag: `git tag v1.x.x && git push --tags`
3. Users update through HACS interface
