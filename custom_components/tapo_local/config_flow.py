"""Config flow for TP-Link Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    SUPPORTED_DEVICE_TYPES,
    SUPPORTED_MODELS,
)
from .protocol import (
    TPLinkLocalConnectionError,
    TPLinkLocalDevice,
    TPLinkLocalDeviceError,
    normalize_model,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_POLL_INTERVAL,
            default=DEFAULT_POLL_INTERVAL,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
        ),
    }
)


async def _probe(host: str) -> dict[str, Any]:
    device = TPLinkLocalDevice(host)
    sysinfo = await device.get_sysinfo()

    model = str(sysinfo.get("model", ""))
    model_base = normalize_model(model)
    device_type = str(sysinfo.get("mic_type", sysinfo.get("type", "")))

    if device_type not in SUPPORTED_DEVICE_TYPES or model_base not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported local device: model={model or 'unknown'}, "
            f"type={device_type or 'unknown'}"
        )

    return sysinfo


class TPLinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TP-Link Local config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a device by LAN address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            try:
                sysinfo = await _probe(host)
            except TPLinkLocalConnectionError:
                errors["base"] = "cannot_connect"
            except TPLinkLocalDeviceError:
                errors["base"] = "device_error"
            except ValueError:
                errors["base"] = "unsupported_device"
            except Exception:
                errors["base"] = "unknown"
            else:
                device_id = str(
                    sysinfo.get("deviceId")
                    or sysinfo.get("device_id")
                    or sysinfo.get("mac")
                    or host
                )
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                model = str(sysinfo.get("model", "TP-Link device"))
                title = str(sysinfo.get("alias") or model)

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        "model": model,
                        "device_type": str(
                            sysinfo.get("mic_type", sysinfo.get("type", ""))
                        ),
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
            self.config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
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
