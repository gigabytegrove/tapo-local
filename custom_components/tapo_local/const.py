"""Constants for Tapo Local."""

DOMAIN = "tapo_local"
NAME = "Tapo Local"

CONF_POLL_INTERVAL = "poll_interval"
CONF_TRANSPORT = "transport"
CONF_SESSION = "session"
CONF_DEVICE_FAMILY = "device_family"
CONF_ENCRYPTION_TYPE = "encryption_type"
CONF_LOGIN_VERSION = "login_version"
CONF_HTTPS = "https"
CONF_HTTP_PORT = "http_port"
CONF_CREDENTIALS_HASH = "credentials_hash"
CONF_CLOUD_USERNAME = "cloud_username"
CONF_CLOUD_PASSWORD = "cloud_password"
CONF_TERMINAL_UUID = "terminal_uuid"
CONF_DL100_DEVICE_ID = "dl100_device_id"

TRANSPORT_XOR = "xor"
TRANSPORT_SMART = "smart"
TRANSPORT_DLKLAP = "dlklap"

# Tapo locks that speak the DL100 local DLKLAP protocol (SMART.TAPOLOCK on
# HTTP port 80). The DL130 reports device_model "DL130(US)" and uses the same
# handshake, getLockStatus/getDeviceRunningInfo methods and lock_status values.
SUPPORTED_LOCK_MODELS = ("DL100", "DL130")


def lock_base_model(model: object) -> str:
    """Return the base lock model without its region suffix, e.g. DL130(US) -> DL130."""
    return str(model or "").split("(", 1)[0].strip().upper()


def is_supported_lock_model(model: object) -> bool:
    """Return True when a reported model is a DLKLAP lock this integration supports."""
    return lock_base_model(model) in SUPPORTED_LOCK_MODELS

DEFAULT_PORT = 9999
DEFAULT_TIMEOUT = 5.0
DEFAULT_POLL_INTERVAL = 5
DEFAULT_LOCK_POLL_INTERVAL = 30
MIN_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 300

SUPPORTED_LEGACY_DEVICE_TYPES = {
    "Plug",
    "WallSwitch",
    "Dimmer",
    "Strip",
    "Bulb",
    "LightStrip",
}

SUPPORTED_SMART_FAMILIES = {
    "SMART.KASAPLUG",
    "SMART.KASASWITCH",
    "SMART.TAPOPLUG",
    "SMART.TAPOBULB",
    "SMART.TAPOSWITCH",
    "SMART.KASAHUB",
    "SMART.TAPOHUB",
}

SUPPORTED_SMART_DEVICE_TYPES = {
    "Plug",
    "WallSwitch",
    "Dimmer",
    "Strip",
    "Bulb",
    "LightStrip",
    "Hub",
    "Fan",
}

PIR_MODULE = "smartlife.iot.PIR"

DL100_SESSION_IMPORT = ".storage/tapo_local_dl100_session_import.json"
DL100_SESSION_STORE_VERSION = 2
KASA_CREDENTIAL_STORE_VERSION = 1
