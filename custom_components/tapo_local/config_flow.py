"""Config flow for TP-Link Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_POLL_INTERVAL,
    CONF_TRANSPORT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    SUPPORTED_DEVICE_TYPES,
    SUPPORTED_MODELS,
    TRANSPORT_XOR,
)
from .discovery import async_identify_device
from .protocol import TPLinkLocalConnectionError


USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


class TPLinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TP-Link Local config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a device by LAN address without cloud authentication."""
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
                ):
                    return self.async_abort(reason="dl100_ble_required")

                errors["base"] = "unsupported_device"

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
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

        current = int(
            self.config_entry.options.get(
                CONF_POLL_INTERVAL,
                DEFAULT_POLL_INTERVAL,
            )
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
