"""Config flow for TP-Link Local."""

from __future__ import annotations

import base64
from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_SESSION,
    CONF_DEVICE_ID,
    CONF_POLL_INTERVAL,
    CONF_TERMINAL_UUID,
    CONF_TRANSPORT,
    DEFAULT_LOCK_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    SUPPORTED_DEVICE_TYPES,
    SUPPORTED_MODELS,
    TRANSPORT_DLKLAP,
    TRANSPORT_XOR,
)
from .discovery import LocalDiscovery, async_identify_device
from .dlklap import (
    Dl100Device,
    DlklapAuthenticationError,
    DlklapProtocolError,
)
from .protocol import (
    TPLinkLocalConnectionError,
    TPLinkLocalDeviceError,
)


def _decode_title(value: Any, fallback: str) -> str:
    """Decode Tapo base64 nicknames when present."""
    if not value:
        return fallback
    text = str(value)
    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8").strip()
        return decoded or fallback
    except Exception:
        return text


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
    }
)

DL100_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


class TPLinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TP-Link Local config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending: LocalDiscovery | None = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a device by LAN address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            try:
                discovery = await async_identify_device(host)
            except TPLinkLocalConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                if (
                    discovery.transport == TRANSPORT_XOR
                    and discovery.device_type in SUPPORTED_DEVICE_TYPES
                    and discovery.model_base in SUPPORTED_MODELS
                ):
                    unique_id = discovery.device_id or host
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                    sysinfo = discovery.sysinfo or {}
                    title = str(sysinfo.get("alias") or discovery.model)
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_HOST: host,
                            "model": discovery.model,
                            "device_type": discovery.device_type,
                            CONF_TRANSPORT: TRANSPORT_XOR,
                        },
                    )

                if (
                    discovery.device_type == "SMART.TAPOLOCK"
                    and discovery.model_base == "DL100"
                    and discovery.encryption_type == "DLKLAP"
                    and discovery.device_id
                ):
                    self._pending = discovery
                    return await self.async_step_dl100()

                errors["base"] = "unsupported_device"

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_dl100(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure a locally discovered DL100's required session bootstrap."""
        if self._pending is None:
            return self.async_abort(reason="cannot_connect")

        errors: dict[str, str] = {}
        if user_input is not None:
            terminal_uuid = str(uuid.uuid4()).upper()
            device = Dl100Device(
                self._pending.host,
                username=user_input[CONF_USERNAME].strip(),
                password=user_input[CONF_PASSWORD],
                device_id=None,
                terminal_uuid=terminal_uuid,
                allow_cloud_bootstrap=True,
            )

            try:
                state = await device.get_state()
            except DlklapAuthenticationError:
                errors["base"] = "invalid_auth"
            except (TPLinkLocalConnectionError, DlklapProtocolError, TPLinkLocalDeviceError):
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                sysinfo = state["sysinfo"]
                unique_id = str(self._pending.device_id)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._pending.host}
                )

                if not device.device_id:
                    errors["base"] = "cannot_connect"
                    return self.async_show_form(
                        step_id="dl100",
                        data_schema=DL100_SCHEMA,
                        errors=errors,
                        description_placeholders={"model": self._pending.model},
                    )

                title = _decode_title(sysinfo.get("nickname"), self._pending.model)
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: self._pending.host,
                        "model": self._pending.model,
                        "device_type": self._pending.device_type,
                        CONF_TRANSPORT: TRANSPORT_DLKLAP,
                        CONF_DEVICE_ID: str(device.device_id),
                        CONF_TERMINAL_UUID: terminal_uuid,
                        CONF_SESSION: device.export_session(),
                    },
                )

        return self.async_show_form(
            step_id="dl100",
            data_schema=DL100_SCHEMA,
            errors=errors,
            description_placeholders={"model": self._pending.model},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explicitly reprovision a DL100 session; never happens during runtime."""
        entry = self._get_reconfigure_entry()
        if entry.data.get(CONF_TRANSPORT) != TRANSPORT_DLKLAP:
            return self.async_abort(reason="unsupported_device")

        errors: dict[str, str] = {}
        if user_input is not None:
            terminal_uuid = str(entry.data.get(CONF_TERMINAL_UUID) or uuid.uuid4()).upper()
            device = Dl100Device(
                entry.data[CONF_HOST],
                username=user_input[CONF_USERNAME].strip(),
                password=user_input[CONF_PASSWORD],
                device_id=entry.data[CONF_DEVICE_ID],
                terminal_uuid=terminal_uuid,
                allow_cloud_bootstrap=True,
            )
            try:
                await device.get_state()
            except DlklapAuthenticationError:
                errors["base"] = "invalid_auth"
            except (TPLinkLocalConnectionError, DlklapProtocolError, TPLinkLocalDeviceError):
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_and_abort(
                    entry,
                    data_updates={
                        CONF_TERMINAL_UUID: terminal_uuid,
                        CONF_SESSION: device.export_session(),
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=DL100_SCHEMA,
            errors=errors,
            description_placeholders={"model": str(entry.data.get("model", "DL100"))},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow."""
        return TPLinkLocalOptionsFlow()


class TPLinkLocalOptionsFlow(config_entries.OptionsFlow):
    """Options flow."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        default = (
            DEFAULT_LOCK_POLL_INTERVAL
            if self.config_entry.data.get(CONF_TRANSPORT) == TRANSPORT_DLKLAP
            else DEFAULT_POLL_INTERVAL
        )
        current = int(
            self.config_entry.options.get(CONF_POLL_INTERVAL, default)
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=current,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
