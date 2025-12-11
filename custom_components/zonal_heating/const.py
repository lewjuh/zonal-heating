"""Constants for the zonal_heating integration."""

from homeassistant.const import Platform

DOMAIN = "zonal_heating"

# Platforms
PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

# Config entry data keys
CONF_ZONES = "zones"
CONF_ZONE_NAME = "name"
CONF_ZONE_THERMOSTAT = "zone_thermostat"
CONF_ROOMS = "rooms"
CONF_ROOM_NAME = "name"
CONF_TRV_ENTITY = "trv_entity"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_PRIORITY = "priority"
CONF_SETTINGS = "settings"

# Settings keys
CONF_TEMP_DIFFERENTIAL = "temp_differential"
CONF_MIN_CYCLE_TIME = "min_cycle_time"
CONF_WINDOW_DELAY = "window_delay"
CONF_PERSON_ENTITIES = "person_entities"
CONF_AWAY_TEMPERATURE = "away_temperature"
CONF_AWAY_MODE_DELAY = "away_mode_delay"
CONF_OVERHEAT_THRESHOLD = "overheat_threshold"

# Default values
DEFAULT_TEMP_DIFFERENTIAL = 0.5  # °C below target to trigger heat
DEFAULT_MIN_CYCLE_TIME = 5  # Minutes between zone state changes
DEFAULT_WINDOW_DELAY = 30  # Seconds to wait after window opens
DEFAULT_PRIORITY = 5  # Default room priority (1-10 scale)
DEFAULT_AWAY_TEMPERATURE = 16.0  # °C temperature when all away
DEFAULT_AWAY_MODE_DELAY = 10  # Minutes to wait before activating away mode
DEFAULT_OVERHEAT_THRESHOLD = 1.0  # °C above target to turn off TRV

# Update intervals
UPDATE_INTERVAL_ZONE_EVAL = 30  # Seconds between zone evaluations
UPDATE_INTERVAL_TEMP_POLL = 60  # Seconds between temperature polling

# Priority range
PRIORITY_MIN = 1
PRIORITY_MAX = 10

# Service names
SERVICE_SET_PRIORITY = "set_priority"
SERVICE_GET_STATS = "get_stats"

# Attributes
ATTR_ZONE_ACTIVE = "zone_active"
ATTR_WINDOW_OPEN = "window_open"
ATTR_HEAT_REQUESTING = "heat_requesting"
ATTR_PRIORITY = "priority"
ATTR_AWAY_MODE = "away_mode"
ATTR_PEOPLE_HOME = "people_home"
ATTR_OVERHEATED = "overheated"
