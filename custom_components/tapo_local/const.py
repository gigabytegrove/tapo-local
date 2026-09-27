"""Constants for TP-Link Local."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "tapo_local"
NAME = "TP-Link Local"

CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_PORT = 9999
DEFAULT_TIMEOUT = 5.0
DEFAULT_POLL_INTERVAL = 5
MIN_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 300

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_POLL_INTERVAL)

SUPPORTED_DEVICE_TYPES = {
    "IOT.SMARTPLUGSWITCH",
}

SUPPORTED_MODELS = {
    "KS200",
    "KS200M",
}

PIR_MODULE = "smartlife.iot.PIR"

ATTR_SYSINFO = "sysinfo"
ATTR_PIR_CONFIG = "pir_config"
ATTR_PIR_ADC = "pir_adc"
