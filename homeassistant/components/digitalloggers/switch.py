"""Support for Digital Loggers DIN III Relays."""
from datetime import timedelta
import logging

import dlipower
import voluptuous as vol

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchDevice
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

CONF_CYCLETIME = "cycletime"
CONF_IGNORE_UNNAMED = "ignore_unnamed_outlets"

DEFAULT_NAME = "DINRelay"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_TIMEOUT = 20
DEFAULT_CYCLETIME = 2
DEFAULT_IGNORE_UNNAMED = False

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=600)
        ),
        vol.Optional(CONF_CYCLETIME, default=DEFAULT_CYCLETIME): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=600)
        ),
        vol.Optional(CONF_IGNORE_UNNAMED, default=DEFAULT_IGNORE_UNNAMED): cv.boolean,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Find and return DIN III Relay switch."""

    host = config.get(CONF_HOST)
    controller_name = config.get(CONF_NAME)
    user = config.get(CONF_USERNAME)
    pswd = config.get(CONF_PASSWORD)
    tout = config.get(CONF_TIMEOUT)
    cycl = config.get(CONF_CYCLETIME)
    ignore_unnamed = config.get(CONF_IGNORE_UNNAMED)

    power_switch = dlipower.PowerSwitch(
        hostname=host, userid=user, password=pswd, timeout=tout, cycletime=cycl
    )

    if not power_switch.verify():
        _LOGGER.error("Could not connect to DIN III Relay")
        return False

    outlets = []
    parent_device = DINRelayDevice(power_switch, host)

    for outlet_number, description, state in power_switch.statuslist():
        if description is None:
            if ignore_unnamed:
                continue
            description = str(outlet_number)
        outlets.append(
            DINRelay(
                controller_name,
                parent_device,
                dlipower.Outlet(parent_device, outlet_number, description, state),
            )
        )

    add_entities(outlets)


class DINRelay(SwitchDevice):
    """Representation of an individual DIN III relay port."""

    def __init__(self, controller_name, parent_device, outlet):
        """Initialize the DIN III Relay switch."""
        self._controller_name = controller_name
        self._parent_device = parent_device
        self._outlet = outlet

        self._outlet_number = self._outlet.outlet_number
        self._name = self._outlet.description
        self._state = self._outlet.state == "ON"

    @property
    def name(self):
        """Return the display name of this relay."""
        return f"{self._controller_name}_{self._name}"

    @property
    def is_on(self):
        """Return true if relay is on."""
        return self._state

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def unique_id(self):
        """Return a unique ID based on the hostname of the power controller and the outlet number."""
        return f"{self._parent_device.hostname}_{self._outlet_number}"

    def turn_on(self, **kwargs):
        """Instruct the relay to turn on."""
        self._outlet.on()

    def turn_off(self, **kwargs):
        """Instruct the relay to turn off."""
        self._outlet.off()

    def update(self):
        """Trigger update for all switches on the parent device."""
        self._parent_device.update()

        outlet_status = self._parent_device.get_outlet_status(self._outlet_number)

        self._name = outlet_status[1] or str(self._outlet_number)
        self._state = outlet_status[2] == "ON"


class DINRelayDevice:
    """Device representation for per device throttling."""

    def __init__(self, power_switch, hostname):
        """Initialize the DINRelay device."""
        self._power_switch = power_switch
        self._statuslist = None
        self.hostname = hostname

    def get_outlet_status(self, outlet_number):
        """Get status of outlet from cached status list."""
        return self._statuslist[outlet_number - 1]

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new state data for this device."""
        self._statuslist = self._power_switch.statuslist()
