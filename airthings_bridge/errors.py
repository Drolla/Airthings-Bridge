"""Exceptions of the Airthings Bridge."""


class BridgeError(Exception):
    """Base class of the Airthings Bridge errors."""


class ConfigError(BridgeError):
    """Invalid configuration."""


class DeviceError(BridgeError):
    """Failed communication with a device."""
