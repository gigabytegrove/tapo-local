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
    SUPPORTED_MODELS,
    TRANSPORT_XOR,
)
from .discovery import async_targeted_tdp_discovery
from .kasa_backend import KasaLocalDevice, TPLinkLocalBackendError


USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


class TPLinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TP-Link Local config flow."""

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a device by address using deterministic local protocols."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            backend = KasaLocalDevice(host)

            try:
                info = await backend.async_probe()
            except TPLinkLocalBackendError:
                # The supported switches did not answer forced XOR. Check
                # targeted TDP only to identify known non-XOR devices such as
                # DL100; this does not use python-kasa discovery/fallback.
                discovery = await async_targeted_tdp_discovery(host)
                if discovery:
                    model = str(discovery.get("device_model") or "")
                    dtype = str(discovery.get("device_type") or "")
                    if model.split("(", 1)[0].strip() == "DL100" and dtype == "SMART.TAPOLOCK":
                        return self.async_abort(reason="dl100_no_local_wifi")
                    errors["base"] = "unsupported_device"
                else:
                    errors["base"] = "cannot_connect"
            else:
                model = str(info["model"])
                model_base = model.split("(", 1)[0].strip()
                if model_base not in SUPPORTED_MODELS:
                    errors["base"] = "unsupported_device"
                else:
                    unique_id = str(info.get("device_id") or host)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                    return self.async_create_entry(
                        title=str(info.get("alias") or model),
                        data={
                            CONF_HOST: host,
                            "model": model,
                            "device_type": str(info.get("device_type") or ""),
                            CONF_TRANSPORT: TRANSPORT_XOR,
                        },
                    )

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
                    vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
