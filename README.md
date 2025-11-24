# Zonal Heating for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/lewjuh/zonal-heating.svg?style=flat-square)](https://github.com/lewjuh/zonal-heating/releases)
[![License](https://img.shields.io/github/license/lewjuh/zonal-heating.svg?style=flat-square)](LICENSE)

A Home Assistant integration for intelligent multi-zone heating control with TRV (thermostatic radiator valve) management.

## Features

- **Multi-Zone Support**: Organize your home into heating zones, each controlled by a zone thermostat
- **Room-Level Control**: Individual TRV control for each room with priority-based heating
- **Window Detection**: Automatic heating pause when windows are open
- **Smart Cycling**: Prevents rapid on/off cycling with configurable minimum cycle times
- **Temperature Differential**: Fine-tune when heating activates based on temperature drop
- **Priority Heating**: Set heating priorities (1-10) for each room
- **Easy Configuration**: Fully configurable through the UI with step-by-step setup
- **Reconfiguration Support**: Edit zones, rooms, and settings without starting over

## What is Zonal Heating?

Zonal heating divides your home into zones (e.g., ground floor, upstairs), each with:
- A **zone thermostat** that controls the heating system for that zone
- Multiple **rooms** with individual TRVs that open/close radiators
- Optional **window sensors** that pause heating when windows are open

This integration coordinates the zone thermostat and room TRVs to ensure efficient, comfortable heating while preventing wasted energy.

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

1. Go to **Settings** → **Devices & Services**
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
- (Optional) Select window/door sensors
- Set the heating priority (1-10, where 10 is highest)

### Step 3: Global Settings
Configure global heating parameters:
- **Temperature Differential**: How far below target before requesting heat (default: 0.5°C)
- **Minimum Cycle Time**: Minimum time between zone thermostat changes (default: 5 minutes)
- **Window Open Delay**: Wait time before pausing heating when window opens (default: 30 seconds)

### Step 4: Add More Zones (Optional)
Repeat for additional zones in your home.

## How It Works

### Zone Control
Each zone monitors all its rooms and:
- Requests heating when any high-priority room needs it
- Prevents rapid cycling with minimum cycle time
- Coordinates with the zone thermostat to turn heating on/off

### Room Control
Each room:
- Opens its TRV when temperature is below target (considering differential)
- Closes TRV when at/above target temperature
- Pauses heating when windows are detected open
- Respects priority settings for coordinated heating

### Priority System
- Rooms with priority 8-10: High priority - will trigger zone heating
- Rooms with priority 4-7: Medium priority - will open TRV when zone is heating
- Rooms with priority 1-3: Low priority - will open TRV when zone is heating

## Reconfiguration

You can edit your configuration at any time:

1. Go to the Zonal Heating integration page
2. Click **Configure**
3. Choose what to edit:
   - Add/edit/delete zones
   - Add/edit/delete rooms
   - Update global settings

## Example Configuration

**Zone: Ground Floor**
- Zone Thermostat: `climate.boiler_ground_floor`
- Rooms:
  - Living Room (TRV: `climate.living_room_trv`, Priority: 10, Windows: `binary_sensor.living_room_window`)
  - Kitchen (TRV: `climate.kitchen_trv`, Priority: 8)
  - Hallway (TRV: `climate.hallway_trv`, Priority: 5)

**Zone: First Floor**
- Zone Thermostat: `climate.boiler_first_floor`
- Rooms:
  - Main Bedroom (TRV: `climate.main_bedroom_trv`, Priority: 10, Windows: `binary_sensor.bedroom_window`)
  - Bedroom 2 (TRV: `climate.bedroom_2_trv`, Priority: 7)
  - Bathroom (TRV: `climate.bathroom_trv`, Priority: 3)

## Requirements

- Home Assistant 2024.1.0 or newer
- Climate entities for zone thermostats
- Climate entities for TRVs
- (Optional) Binary sensor entities for windows/doors

## Troubleshooting

### Heating not activating
- Check that high-priority rooms (8-10) have temperature below target
- Verify zone thermostat entity is correct
- Check minimum cycle time hasn't prevented activation

### TRV not opening
- Verify TRV entity is correct and available
- Check if window sensor is triggering pause
- Ensure room temperature is below target minus differential

### Enable debug logging
Add to your `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.zonal_heating: debug
```

## Support

- [Report Issues](https://github.com/lewjuh/zonal-heating/issues)
- [Feature Requests](https://github.com/lewjuh/zonal-heating/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Developed by [@lewjuh](https://github.com/lewjuh)
