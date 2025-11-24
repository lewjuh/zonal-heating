# Zonal Heating

Intelligent multi-zone heating control for Home Assistant with TRV management.

## Key Features

✅ **Multi-Zone Support** - Organize your home into heating zones
✅ **Smart TRV Control** - Individual radiator valve management per room
✅ **Window Detection** - Automatic heating pause when windows open
✅ **Priority-Based Heating** - Set room priorities (1-10) for efficient heating
✅ **Anti-Cycling Protection** - Prevents rapid on/off switching
✅ **Easy Configuration** - Complete UI-based setup, no YAML required
✅ **Reconfigurable** - Edit zones and rooms anytime

## Quick Start

After installation:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Zonal Heating"
4. Follow the step-by-step configuration:
   - Add your heating zones
   - Add rooms with TRVs to each zone
   - Configure global settings
   - Done!

## How It Works

**Zonal heating** divides your home into zones (e.g., ground floor, upstairs). Each zone has:
- A main thermostat that controls the heating system
- Multiple rooms with individual TRVs (thermostatic radiator valves)
- Optional window sensors for each room

The integration coordinates everything to ensure:
- High-priority rooms get heating when needed
- Low-priority rooms benefit when heating is already on
- Windows open = heating paused automatically
- No rapid on/off cycling that stresses your boiler

## Configuration Example

**Ground Floor Zone:**
- Living Room (Priority 10) ← Always gets heating when cold
- Kitchen (Priority 8) ← High priority
- Hallway (Priority 5) ← Opens TRV when heating is on

## Requirements

- Home Assistant 2024.1.0+
- Climate entities for zone thermostats
- Climate entities for TRVs
- (Optional) Binary sensors for windows

---

For full documentation, see the [README](https://github.com/lewjuh/zonal-heating).
