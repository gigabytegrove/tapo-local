"""Constants for TP-Link Local."""

from __future__ import annotations

DOMAIN = "tapo_local"
NAME = "TP-Link Local"

CONF_POLL_INTERVAL = "poll_interval"
CONF_TRANSPORT = "transport"
CONF_DEVICE_ID = "device_id"
CONF_TERMINAL_UUID = "terminal_uuid"
CONF_CONTROL_KEY = "control_key"

TRANSPORT_XOR = "xor"
TRANSPORT_DLKLAP = "dlklap"

DEFAULT_PORT = 9999
DEFAULT_TIMEOUT = 5.0
DEFAULT_POLL_INTERVAL = 5
DEFAULT_LOCK_POLL_INTERVAL = 30
MIN_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 300

SUPPORTED_DEVICE_TYPES = {
    "IOT.SMARTPLUGSWITCH",
}

SUPPORTED_MODELS = {
    "KS200",
    "KS200M",
}

PIR_MODULE = "smartlife.iot.PIR"
