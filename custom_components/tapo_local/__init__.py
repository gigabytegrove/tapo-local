"""Tapo Local Home Assistant integration."""

from __future__ import annotations

import logging
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.importlib import async_import_module
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CREDENTIALS_HASH,
    CONF_CLOUD_PASSWORD,
    CONF_CLOUD_USERNAME,
    CONF_DL100_DEVICE_ID,
    CONF_TERMINAL_UUID,
    CONF_DEVICE_FAMILY,
    CONF_ENCRYPTION_TYPE,
    CONF_HTTPS,
    CONF_HTTP_PORT,
    CONF_LOGIN_VERSION,
    CONF_SESSION,
    CONF_TRANSPORT,
    DL100_SESSION_STORE_VERSION,
    DOMAIN,
    KASA_CREDENTIAL_STORE_VERSION,
    TRANSPORT_DLKLAP,
    TRANSPORT_SMART,
)
from .dependency import TPLinkLocalDependencyError, async_ensure_kasa

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Migrate older Tapo Local config entries to the current schema."""
    _LOGGER.debug(
        "Migrating Tapo Local entry %s from version %s.%s",
        entry.title,
        entry.version,
        entry.minor_version,
    )

    if entry.version > 4:
        _LOGGER.error(
            "Cannot migrate Tapo Local entry %s from future version %s",
            entry.title,
            entry.version,
        )
        return False

    # Versions 1 and 2 already stored the host/model/device_type/transport
    # fields used by the XOR runtime. Version 3 added DL100. Version 4 adds
    # authenticated SMART transport metadata. Existing entries need no
    # destructive data transformation.
    if entry.version < 4:
        hass.config_entries.async_update_entry(entry, version=4)

    _LOGGER.debug(
        "Migration of Tapo Local entry %s to version %s.%s successful",
        entry.title,
        entry.version,
        entry.minor_version,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tapo Local from a config entry."""
    is_dl100 = entry.data.get(CONF_TRANSPORT) == TRANSPORT_DLKLAP

    # DL100 has its own local DLKLAP backend and must not depend on
    # python-kasa being healthy. Switch entries still use the managed
    # python-kasa runtime.
    if not is_dl100:
        try:
            await async_ensure_kasa(hass)
        except TPLinkLocalDependencyError as exc:
            raise ConfigEntryNotReady(str(exc)) from exc

    coordinator_module = await async_import_module(
        hass, f"{__package__}.coordinator"
    )
    TPLinkLocalCoordinator = coordinator_module.TPLinkLocalCoordinator

    if is_dl100:
        dl100_module = await async_import_module(
            hass, f"{__package__}.dl100_backend"
        )
        DL100LocalDevice = dl100_module.DL100LocalDevice
        auth_module = await async_import_module(
            hass, f"{__package__}.dl100_auth"
        )
        establish_session = auth_module.establish_session

        store: Store[dict] = Store(
            hass,
            DL100_SESSION_STORE_VERSION,
            f"{DOMAIN}.dl100_session.{entry.entry_id}",
            private=True,
            atomic_writes=True,
        )
        stored = await store.async_load()
        private_data = dict(stored) if isinstance(stored, dict) else {}

        # Migrate setup-time sensitive values into the private Store.
        for key in (
            CONF_SESSION,
            CONF_CLOUD_USERNAME,
            CONF_CLOUD_PASSWORD,
            CONF_TERMINAL_UUID,
            CONF_DL100_DEVICE_ID,
        ):
            if key not in private_data and entry.data.get(key) is not None:
                private_data[key] = entry.data[key]

        session_state = private_data.get(CONF_SESSION)
        username = private_data.get(CONF_CLOUD_USERNAME)
        password = private_data.get(CONF_CLOUD_PASSWORD)
        terminal_uuid = private_data.get(CONF_TERMINAL_UUID)
        device_id = private_data.get(CONF_DL100_DEVICE_ID)

        async def _save_private_session(state: dict) -> None:
            private_data[CONF_SESSION] = state
            await store.async_save(private_data)

        async def _refresh_dl100_session() -> dict:
            if not username or not password:
                raise RuntimeError(
                    "DL100 owner credentials are unavailable for automatic reauthentication"
                )
            provisioned = await hass.async_add_executor_job(
                partial(
                    establish_session,
                    entry.data[CONF_HOST],
                    str(username),
                    str(password),
                    terminal_uuid=str(terminal_uuid) if terminal_uuid else None,
                    device_id=str(device_id) if device_id else None,
                )
            )
            private_data[CONF_SESSION] = provisioned["session"]
            private_data[CONF_TERMINAL_UUID] = provisioned["terminal_uuid"]
            private_data[CONF_DL100_DEVICE_ID] = provisioned["device_id"]
            await store.async_save(private_data)
            return provisioned["session"]

        if not isinstance(session_state, dict):
            if username and password:
                try:
                    session_state = await _refresh_dl100_session()
                except Exception as exc:
                    raise ConfigEntryNotReady(
                        f"DL100 automatic session provisioning failed: {exc}"
                    ) from exc
            else:
                raise ConfigEntryNotReady(
                    "DL100 session and owner credentials are missing; re-add the device"
                )

        try:
            device = DL100LocalDevice(
                entry.data[CONF_HOST],
                session_state=session_state,
                session_saver=_save_private_session,
                session_refresher=_refresh_dl100_session if username and password else None,
            )
        except Exception as exc:
            raise ConfigEntryNotReady(f"DL100 local session is invalid: {exc}") from exc
    else:
        kasa_module = await async_import_module(
            hass, f"{__package__}.kasa_backend"
        )
        KasaLocalDevice = kasa_module.KasaLocalDevice

        if entry.data.get(CONF_TRANSPORT) == TRANSPORT_SMART:
            credential_store: Store[dict] = Store(
                hass,
                KASA_CREDENTIAL_STORE_VERSION,
                f"{DOMAIN}.kasa_credentials.{entry.entry_id}",
                private=True,
                atomic_writes=True,
            )
            stored_credentials = await credential_store.async_load()
            credentials_hash = None
            if isinstance(stored_credentials, dict):
                credentials_hash = stored_credentials.get(CONF_CREDENTIALS_HASH)
            if credentials_hash is None:
                credentials_hash = entry.data.get(CONF_CREDENTIALS_HASH)

            if not credentials_hash:
                raise ConfigEntryNotReady(
                    "Local device credential hash is missing; re-add the device"
                )

            device = KasaLocalDevice(
                entry.data[CONF_HOST],
                device_family=entry.data[CONF_DEVICE_FAMILY],
                encryption_type=entry.data[CONF_ENCRYPTION_TYPE],
                login_version=entry.data.get(CONF_LOGIN_VERSION),
                https=bool(entry.data.get(CONF_HTTPS, False)),
                http_port=entry.data.get(CONF_HTTP_PORT),
                credentials_hash=str(credentials_hash),
            )
        else:
            device = KasaLocalDevice(entry.data[CONF_HOST])

    coordinator = TPLinkLocalCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    if entry.data.get(CONF_TRANSPORT) == TRANSPORT_SMART:
        await credential_store.async_save(
            {CONF_CREDENTIALS_HASH: str(credentials_hash)}
        )
        if CONF_CREDENTIALS_HASH in entry.data:
            new_data = dict(entry.data)
            new_data.pop(CONF_CREDENTIALS_HASH, None)
            hass.config_entries.async_update_entry(entry, data=new_data)

    if entry.data.get(CONF_TRANSPORT) == TRANSPORT_DLKLAP:
        private_data[CONF_SESSION] = device.export_session()
        await store.async_save(private_data)

        # Keep cloud credentials and session keys out of the normal config entry.
        sensitive_keys = {
            CONF_SESSION,
            CONF_CLOUD_USERNAME,
            CONF_CLOUD_PASSWORD,
            CONF_TERMINAL_UUID,
            CONF_DL100_DEVICE_ID,
        }
        if any(key in entry.data for key in sensitive_keys):
            new_data = {
                key: value
                for key, value in entry.data.items()
                if key not in sensitive_keys
            }
            hass.config_entries.async_update_entry(entry, data=new_data)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    if hasattr(device, "async_disconnect"):
        entry.async_on_unload(device.async_disconnect)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
