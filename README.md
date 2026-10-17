# Zonal Heating for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/lewjuh/zonal-heating.svg?style=flat-square)](https://github.com/lewjuh/zonal-heating/releases)
[![License](https://img.shields.io/github/license/lewjuh/zonal-heating.svg?style=flat-square)](LICENSE)

A Home Assistant integration for multi-zone heating control with TRV (thermostatic radiator valve) coordination.

## How It Works

You set a temperature on a room. The room holds it. No schedules, no away mode, no system overriding your chosen temperature behind your back.

The integration coordinates your zone thermostat (boiler) with individual room TRVs:

1. You set a target temperature on a room via the virtual climate entity
2. The integration forwards it to the physical TRV
3. The room state machine starts asking for heat when the room drops below target minus differential, and keeps asking until it reaches target
4. The zone state machine watches all rooms -- if any room needs heat, it turns on the zone thermostat
5. When all rooms are satisfied, the zone thermostat turns off

That's it. Four temperature write points, one clear control flow.

## Features

- **Multi-Zone Support** -- organise your home into heating zones, each controlled by a zone thermostat
- **Room-Level Control** -- individual TRV management for each room
- **Window Detection** -- heating demand suppressed when windows are open (with configurable delay to avoid false triggers)
- **Smart Cycling** -- prevents boiler short-cycling with configurable minimum on and off times
- **Temperature Differential** -- how far below target a room must drop before heating restarts (hysteresis, so the boiler does not chatter around the target)
- **External Temperature Sensors** -- use a separate sensor for more accurate room readings
- **Calibration Sync** -- sync external sensor readings to TRV via calibration offset or direct input
- **Diagnostic Sensors** -- detailed sensors for monitoring and debugging
- **Custom Dashboard Card** -- built-in Lovelace card for visual heating status
- **UI Configuration** -- fully configurable through the Home Assistant UI with step-by-step setup
- **Reconfiguration** -- edit zones, rooms, and settings without starting over

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/lewjuh/zonal-heating`
5. Select category: "Integration"
6. Click "Add"
7. Click "Install" on the Zonal Heating card
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/zonal_heating` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Zonal Heating"
4. Follow the configuration flow:

### Step 1: Add Zones

- Give your zone a name (e.g., "Ground Floor", "Upstairs")
- Select the main thermostat that controls heating for this zone

### Step 2: Add Rooms to Zone

For each room in the zone:
- Enter the room name (e.g., "Living Room", "Bedroom")
- Select the TRV climate entity for that room
- (Optional) Select an external temperature sensor for more accurate readings
- (Optional) Select window/door sensors
- Set the heating priority (1-10). This is currently informational only: it is shown on the entity but does not change heating decisions

### Step 3: Global Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Temperature Differential | 0.25°C | How far below target a room must drop before heat is requested again; once requesting, it continues until target is reached |
| Minimum On Time | 10 minutes | Once the zone thermostat turns on, how long it stays on at least |
| Minimum Off Time | 10 minutes | Once the zone thermostat turns off, how long it stays off at least |
| Window Open Delay | 30 seconds | Wait time before suppressing heat when window opens |
| Calibration Sync | Off | Sync external sensor temperature to TRV calibration |

### Step 4: Add More Zones (Optional)

Repeat for additional zones in your home.

## Zone and Room Behaviour

### Zone State Machine

The zone monitors all its rooms and:
- Turns the zone thermostat **on** when any room needs heat and its TRV is still open
- Turns the zone thermostat **off** when no rooms need heat
- Holds the zone on for at least the minimum on time and off for at least the minimum off time, so the boiler is not short-cycled
- Automatically retries when a change is held back
- Turns the zone thermostat on in `heat` mode with a target of current + 5°C, capped at the thermostat's maximum (ensures the boiler fires)
- Treats any active mode other than `off` (e.g. `auto`) as on, and switches it off when no rooms need heat

### Room State Machine

Each room:
- Starts reporting `needs_heat` when current temperature drops below target minus differential, and keeps reporting it until the room reaches target (as long as the climate entity is on and no window is confirmed open)
- Monitors the TRV entity for temperature and state changes
- Uses an external temperature sensor if configured (overrides the TRV's built-in sensor)
- Handles window detection with a configurable delay to prevent false triggers from brief openings
- Stops requesting heat when the TRV goes unavailable (prevents running the boiler on stale data)
- Does not hold the zone on while its TRV is satisfied (TRV reports `idle`, or its own reading is at its target), since the valve is closed and the boiler would heat nothing
- Stops holding the zone on if it has not warmed by 0.2°C after an hour of zone heating, and retries two hours later or when its target changes. A warning is logged so the TRV or radiator can be checked

### Window Detection

When a window sensor triggers:
1. The room notes the window is open but continues requesting heat during the delay period
2. After the configured delay (default 30s), if the window is still open, the room confirms it and suppresses heat requests
3. The zone re-evaluates immediately and may turn off if no other rooms need heat
4. When the window closes, the room resumes heat requests and the zone re-evaluates

The TRV target temperature is never changed by window detection -- it only suppresses the room's demand signal to the zone.

### Calibration Sync

When enabled with an external temperature sensor, the integration syncs the external reading to the TRV so it uses the more accurate measurement. It tries these methods in order:

1. **Direct external temp input** -- sets the external sensor number entity on the TRV (e.g., Sonoff TRVZB)
2. **Calibration offset** -- calculates and sets a local temperature calibration offset

The offset is only recalculated once the TRV has reported a temperature taken after the previous offset was applied, so it does not overshoot.

The TRV's sync entities are found through the entity registry, so they are picked up even if they have no value yet when Home Assistant starts. Syncing starts as soon as they report one.

## Reconfiguration

You can edit your configuration at any time:

1. Go to the Zonal Heating integration page
2. Click **Configure**
3. Choose what to edit:
   - Add/edit/delete zones
   - Add/edit/delete rooms
4. To update global settings, click the three-dot menu and select **Configure** on the options flow

## Dashboard Card

The integration includes a custom Lovelace card for visual heating status.

### Adding the Card

1. After installing the integration, add a new card to your dashboard
2. Select "Custom: Zonal Heating Card" from the card picker
3. Configure the card with your zone sensor

### Manual Configuration

```yaml
type: custom:zonal-heating-card
zone_sensor: sensor.zonal_heating_ground_floor_status
title: Ground Floor Heating
show_debug: false
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `zone_sensor` | Yes | - | The zone diagnostic sensor entity |
| `title` | No | Zone name | Card title |
| `show_debug` | No | `false` | Show debug information by default |

### Card Features

- **Zone Status** -- shows heating/idle status with colour coding
- **Room List** -- all rooms with current and target temperatures
- **Status Reasons** -- clear explanations for why each room is in its current state
- **Debug Toggle** -- click to see detailed diagnostic information

The integration automatically registers the card resource. If you need to add it manually, go to **Settings** > **Dashboards** > three-dot menu > **Resources** and add `/zonal_heating/zonal-heating-card.js` as a JavaScript Module.

## Diagnostic Sensors

### Zone Sensor

Entity: `sensor.zonal_heating_<zone_name>_status`

**States:**
- `heating` -- zone thermostat is on, at least one room needs heat
- `idle` -- all rooms satisfied, zone thermostat off

**Key attributes:**
- `zone_is_on` -- whether the zone thermostat is currently on
- `rooms_needing_heat_count` -- number of rooms requesting heat
- `rooms_needing_heat` -- list of room names needing heat
- `cycle_time_blocking` -- whether the minimum on or off time is preventing a state change
- `time_until_cycle_allowed_minutes` -- time remaining until changes are allowed
- `reason` -- human-readable explanation of current state
- `detailed_rooms` -- full details of all rooms including temperatures and deficits

### Room Sensor

Entity: `sensor.zonal_heating_<zone_name>_<room_name>_status` (installs from before v1.8 keep `sensor.zonal_heating_<room_name>_status`)

**States:**
- `needs_heat` -- room is heating up to its target
- `trv_satisfied` -- room is below target but its TRV has closed its valve, so it is not holding the zone on
- `stalled` -- room has not warmed despite zone heating, so its demand is ignored for now
- `satisfied` -- room is at target, or within the differential below it
- `window_open` -- window confirmed open, heat requests suppressed
- `off` -- climate entity is off

**Key attributes:**
- `current_temp` -- current room temperature
- `target_temp` -- target temperature
- `temp_differential` -- configured differential
- `temperature_deficit` -- degrees below target
- `heat_threshold` -- temperature below which heating starts again
- `reason` -- human-readable explanation of current state

## Example Setup

**Zone: Ground Floor**
- Zone Thermostat: `climate.boiler_ground_floor`
- Rooms:
  - Living Room (TRV: `climate.living_room_trv`, Sensor: `sensor.living_room_temp`, Windows: `binary_sensor.living_room_window`)
  - Kitchen (TRV: `climate.kitchen_trv`)
  - Hallway (TRV: `climate.hallway_trv`)

**Zone: First Floor**
- Zone Thermostat: `climate.boiler_first_floor`
- Rooms:
  - Main Bedroom (TRV: `climate.main_bedroom_trv`, Sensor: `sensor.bedroom_temp`, Windows: `binary_sensor.bedroom_window`)
  - Bedroom 2 (TRV: `climate.bedroom_2_trv`)
  - Bathroom (TRV: `climate.bathroom_trv`)

## Requirements

- Home Assistant 2024.11.0 or newer
- Climate entities for zone thermostats
- Climate entities for TRVs
- (Optional) Temperature sensor entities for more accurate room readings
- (Optional) Binary sensor entities for windows/doors

## Troubleshooting

### Heating not activating
- Check diagnostic sensors -- look at the `reason` attribute for an explanation
- Verify at least one room reports `needs_heat`
- Check if the minimum on/off time is blocking (`cycle_time_blocking` attribute)
- A room in `trv_satisfied` won't turn the zone on: its TRV thinks the room is warm. Enable Calibration Sync with an external sensor so the TRV and the room agree
- Ensure the zone thermostat entity is correct and available

### TRV not responding
- Check the TRV entity is available in Home Assistant
- Check logs for "Failed to set TRV target temperature" messages

### Window detection not working
- Check that the window sensor reports `on` when open
- The delay (default 30s) means heating won't stop immediately -- this is intentional to avoid false triggers
- Check the room diagnostic sensor's `window_open` and `window_open_confirmed` attributes

### Enable debug logging

Add to your `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.zonal_heating: debug
```

Key log messages to search for:
- `ZONE EVALUATION` -- zone decision points
- `MIN ON TIME` / `MIN OFF TIME` -- cycling protection
- `Not warming` -- a room's demand was dropped by the stall guard
- `Window opened` / `Window open confirmed` -- window detection
- `Heating need changed` -- room heat demand changes

## Support

- [Report Issues](https://github.com/lewjuh/zonal-heating/issues)
- [Feature Requests](https://github.com/lewjuh/zonal-heating/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Developed by [@lewjuh](https://github.com/lewjuh)
