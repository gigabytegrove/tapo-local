"""TP-Link Local Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.importlib import async_import_module
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CREDENTIALS_HASH,
    CONF_DEVICE_FAMILY,
    CONF_ENCRYPTION_TYPE,
    CONF_HTTPS,
    CONF_HTTP_PORT,
    CONF_LOGIN_VERSION,
    CONF_SESSION,
    CONF_TRANSPORT,
    DL100_SESSION_STORE_VERSION,
    DOMAIN,
    TRANSPORT_DLKLAP,
    TRANSPORT_SMART,
)
from .dependency import TPLinkLocalDependencyError, async_ensure_kasa

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
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
    """Migrate older TP-Link Local config entries to the current schema."""
    _LOGGER.debug(
        "Migrating TP-Link Local entry %s from version %s.%s",
        entry.title,
        entry.version,
        entry.minor_version,
    )

    if entry.version > 3:
        _LOGGER.error(
            "Cannot migrate TP-Link Local entry %s from future version %s",
            entry.title,
            entry.version,
        )
        return False

    # Versions 1 and 2 already stored the same host/model/device_type/transport
    # fields used by the python-kasa XOR runtime. Version 3 adds DL100 setup but
    # requires no destructive data transformation for existing switch entries.
    if entry.version < 3:
        hass.config_entries.async_update_entry(entry, version=3)

    _LOGGER.debug(
        "Migration of TP-Link Local entry %s to version %s.%s successful",
        entry.title,
        entry.version,
        entry.minor_version,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TP-Link Local from a config entry."""
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

        store: Store[dict] = Store(
            hass,
            DL100_SESSION_STORE_VERSION,
            f"{DOMAIN}.dl100_session.{entry.entry_id}",
            private=True,
            atomic_writes=True,
        )
        stored = await store.async_load()
        session_state = None
        if isinstance(stored, dict) and isinstance(stored.get("session"), dict):
            session_state = stored["session"]
        elif isinstance(entry.data.get(CONF_SESSION), dict):
            session_state = entry.data[CONF_SESSION]

        if session_state is None:
            raise ConfigEntryNotReady(
                "DL100 local session is missing; re-add the device with a session import"
            )

        async def _save_session(state: dict) -> None:
            await store.async_save({"session": state})

        try:
            device = DL100LocalDevice(
                entry.data[CONF_HOST],
                session_state=session_state,
                session_saver=_save_session,
            )
        except Exception as exc:
            raise ConfigEntryNotReady(f"DL100 local session is invalid: {exc}") from exc
    else:
        kasa_module = await async_import_module(
            hass, f"{__package__}.kasa_backend"
        )
        KasaLocalDevice = kasa_module.KasaLocalDevice

        if entry.data.get(CONF_TRANSPORT) == TRANSPORT_SMART:
            device = KasaLocalDevice(
                entry.data[CONF_HOST],
                device_family=entry.data[CONF_DEVICE_FAMILY],
                encryption_type=entry.data[CONF_ENCRYPTION_TYPE],
                login_version=entry.data.get(CONF_LOGIN_VERSION),
                https=bool(entry.data.get(CONF_HTTPS, False)),
                http_port=entry.data.get(CONF_HTTP_PORT),
                credentials_hash=entry.data[CONF_CREDENTIALS_HASH],
            )
        else:
            device = KasaLocalDevice(entry.data[CONF_HOST])

    coordinator = TPLinkLocalCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    if entry.data.get(CONF_TRANSPORT) == TRANSPORT_DLKLAP:
        latest = device.export_session()
        await _save_session(latest)
        if CONF_SESSION in entry.data:
            new_data = dict(entry.data)
            new_data.pop(CONF_SESSION, None)
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
