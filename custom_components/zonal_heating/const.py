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
CONF_TEMP_SENSOR = "temp_sensor"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_PRIORITY = "priority"
CONF_SETTINGS = "settings"

# Settings keys
CONF_TEMP_DIFFERENTIAL = "temp_differential"
CONF_MIN_ON_TIME = "min_on_time"
CONF_MIN_OFF_TIME = "min_off_time"
CONF_WINDOW_DELAY = "window_delay"
CONF_CALIBRATION_SYNC = "calibration_sync"

# Default values
DEFAULT_TEMP_DIFFERENTIAL = 0.25  # °C below target to trigger heat
DEFAULT_MIN_ON_TIME = 10  # Minutes a zone stays on before it may turn off
DEFAULT_MIN_OFF_TIME = 10  # Minutes a zone stays off before it may turn on
DEFAULT_WINDOW_DELAY = 30  # Seconds to wait after window opens
DEFAULT_PRIORITY = 5  # Default room priority (1-10 scale)
DEFAULT_CALIBRATION_SYNC = False  # Sync external temp to TRV via calibration offset

# Priority range
PRIORITY_MIN = 1
PRIORITY_MAX = 10

# Attributes
ATTR_ZONE_ACTIVE = "zone_active"
ATTR_WINDOW_OPEN = "window_open"
ATTR_HEAT_REQUESTING = "heat_requesting"
ATTR_PRIORITY = "priority"
