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
3. The room state machine monitors whether the room needs heat (current temp below target minus differential)
4. The zone state machine watches all rooms -- if any room needs heat, it turns on the zone thermostat
5. When all rooms are satisfied, the zone thermostat turns off

That's it. Four temperature write points, one clear control flow.

## Features

- **Multi-Zone Support** -- organise your home into heating zones, each controlled by a zone thermostat
- **Room-Level Control** -- individual TRV management for each room
- **Window Detection** -- heating demand suppressed when windows are open (with configurable delay to avoid false triggers)
- **Smart Cycling** -- prevents rapid boiler on/off with configurable minimum cycle time
- **Temperature Differential** -- fine-tune when heating activates based on temperature drop below target
- **External Temperature Sensors** -- use a separate sensor for more accurate room readings
- **Calibration Sync** -- sync external sensor readings to TRV via calibration offset or direct input
- **MQTT Direct Control** -- automatic Zigbee2MQTT detection for more reliable TRV communication
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
- Set the heating priority (1-10)

### Step 3: Global Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Temperature Differential | 0.25°C | How far below target before requesting heat |
| Minimum Cycle Time | 5 minutes | Minimum time between zone thermostat on/off changes |
| Window Open Delay | 30 seconds | Wait time before suppressing heat when window opens |
| Calibration Sync | Off | Sync external sensor temperature to TRV calibration |

### Step 4: Add More Zones (Optional)

Repeat for additional zones in your home.

## Zone and Room Behaviour

### Zone State Machine

The zone monitors all its rooms and:
- Turns the zone thermostat **on** when any room needs heat
- Turns the zone thermostat **off** when no rooms need heat
- Prevents rapid cycling with a minimum cycle time between state changes
- Automatically retries when blocked by the cycle timer
- Sets the zone thermostat target to current + 5°C when turning on (ensures the boiler fires)

### Room State Machine

Each room:
- Reports `needs_heat` when current temperature is below target minus differential, the climate entity is on, and the window is not confirmed open
- Monitors the TRV entity for temperature and state changes
- Uses an external temperature sensor if configured (overrides the TRV's built-in sensor)
- Handles window detection with a configurable delay to prevent false triggers from brief openings
- Stops requesting heat when the TRV goes unavailable (prevents running the boiler on stale data)

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
3. **MQTT direct** -- publishes the calibration offset directly via Zigbee2MQTT MQTT

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
- `cycle_time_blocking` -- whether min cycle time is preventing a state change
- `time_until_cycle_allowed_minutes` -- time remaining until changes are allowed
- `reason` -- human-readable explanation of current state
- `detailed_rooms` -- full details of all rooms including temperatures and deficits

### Room Sensor

Entity: `sensor.zonal_heating_<room_name>_status`

**States:**
- `needs_heat` -- room temperature is below heating threshold
- `satisfied` -- temperature at or above threshold
- `window_open` -- window confirmed open, heat requests suppressed
- `off` -- climate entity is off

**Key attributes:**
- `current_temp` -- current room temperature
- `target_temp` -- target temperature
- `temp_differential` -- configured differential
- `temperature_deficit` -- degrees below target
- `heat_threshold` -- temperature below which heating activates
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

- Home Assistant 2024.1.0 or newer
- Climate entities for zone thermostats
- Climate entities for TRVs
- (Optional) Temperature sensor entities for more accurate room readings
- (Optional) Binary sensor entities for windows/doors

## Troubleshooting

### Heating not activating
- Check diagnostic sensors -- look at the `reason` attribute for an explanation
- Verify at least one room reports `needs_heat`
- Check if minimum cycle time is blocking (`cycle_time_blocking` attribute)
- Ensure the zone thermostat entity is correct and available

### TRV not responding
- Check the TRV entity is available in Home Assistant
- If using Zigbee2MQTT, the integration should auto-detect and use direct MQTT control
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
- `MIN CYCLE TIME` -- cycling protection
- `Window opened` / `Window open confirmed` -- window detection
- `Heating need changed` -- room heat demand changes

## Support

- [Report Issues](https://github.com/lewjuh/zonal-heating/issues)
- [Feature Requests](https://github.com/lewjuh/zonal-heating/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Developed by [@lewjuh](https://github.com/lewjuh)
