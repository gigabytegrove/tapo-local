"""Constants for TAPO Local."""

DOMAIN = "tapo_local"
NAME = "TAPO Local"

CONF_POLL_INTERVAL = "poll_interval"
CONF_TRANSPORT = "transport"
CONF_SESSION = "session"
CONF_DEVICE_FAMILY = "device_family"
CONF_ENCRYPTION_TYPE = "encryption_type"
CONF_LOGIN_VERSION = "login_version"
CONF_HTTPS = "https"
CONF_HTTP_PORT = "http_port"
CONF_CREDENTIALS_HASH = "credentials_hash"

TRANSPORT_XOR = "xor"
TRANSPORT_SMART = "smart"
TRANSPORT_DLKLAP = "dlklap"

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
}

SUPPORTED_SMART_DEVICE_TYPES = {
    "Plug",
    "WallSwitch",
    "Dimmer",
    "Strip",
    "Bulb",
    "LightStrip",
}

PIR_MODULE = "smartlife.iot.PIR"

DL100_SESSION_IMPORT = ".storage/tapo_local_dl100_session_import.json"
DL100_SESSION_STORE_VERSION = 1
KASA_CREDENTIAL_STORE_VERSION = 1
