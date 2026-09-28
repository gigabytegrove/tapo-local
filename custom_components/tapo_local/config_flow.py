"""Config flow for TP-Link Local."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_POLL_INTERVAL,
    CONF_SESSION,
    CONF_TRANSPORT,
    DEFAULT_LOCK_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DL100_SESSION_IMPORT,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    SUPPORTED_MODELS,
    TRANSPORT_DLKLAP,
    TRANSPORT_XOR,
)
from .dependency import TPLinkLocalDependencyError, async_ensure_kasa
from .discovery import async_targeted_tdp_discovery


USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})
DL100_RETRY_SCHEMA = vol.Schema({})


def _read_session_import(path: str) -> dict[str, Any]:
    from .dl100_backend import extract_session_state

    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("DL100 session import must be a JSON object")
    return extract_session_state(payload)


def _remove_session_import(path: str) -> None:
    Path(path).unlink(missing_ok=True)


class TPLinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TP-Link Local config flow."""

    VERSION = 3

    def __init__(self) -> None:
        self._pending_dl100: dict[str, Any] | None = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a device by address using deterministic local protocols."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await async_ensure_kasa(self.hass)
            except TPLinkLocalDependencyError:
                errors["base"] = "dependency_unavailable"
            else:
                from .kasa_backend import KasaLocalDevice, TPLinkLocalBackendError

                host = user_input[CONF_HOST].strip()
                backend = KasaLocalDevice(host)

                try:
                    info = await backend.async_probe()
                except TPLinkLocalBackendError:
                    discovery = await async_targeted_tdp_discovery(host)
                    if discovery:
                        model = str(discovery.get("device_model") or "")
                        dtype = str(discovery.get("device_type") or "")
                        if (
                            model.split("(", 1)[0].strip() == "DL100"
                            and dtype == "SMART.TAPOLOCK"
                        ):
                            self._pending_dl100 = {
                                "host": host,
                                "model": model or "DL100",
                                "device_type": dtype,
                                "device_id": str(
                                    discovery.get("device_id")
                                    or discovery.get("deviceId")
                                    or host
                                ),
                            }
                            return await self.async_step_dl100_session()
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
                        self._abort_if_unique_id_configured(
                            updates={CONF_HOST: host}
                        )

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

    async def async_step_dl100_session(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Import and verify an existing authorized DL100 LAN session."""
        if self._pending_dl100 is None:
            return self.async_abort(reason="cannot_connect")

        import_path = self.hass.config.path(DL100_SESSION_IMPORT)
        errors: dict[str, str] = {}

        try:
            session_state = await self.hass.async_add_executor_job(
                _read_session_import, import_path
            )
        except FileNotFoundError:
            errors["base"] = "dl100_session_missing"
        except Exception:
            errors["base"] = "dl100_session_invalid"
        else:
            from .dl100_backend import DL100LocalDevice, DL100LocalError

            device = DL100LocalDevice(
                self._pending_dl100["host"],
                session_state=session_state,
            )
            try:
                state = await device.get_state()
            except DL100LocalError:
                errors["base"] = "dl100_session_rejected"
            except Exception:
                errors["base"] = "unknown"
            else:
                latest_session = device.export_session()
                unique_id = self._pending_dl100["device_id"]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._pending_dl100["host"]}
                )

                sysinfo = state["sysinfo"]
                title = str(
                    sysinfo.get("nickname")
                    or sysinfo.get("device_name")
                    or self._pending_dl100["model"]
                )

                await self.hass.async_add_executor_job(
                    _remove_session_import, import_path
                )

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: self._pending_dl100["host"],
                        "model": self._pending_dl100["model"],
                        "device_type": self._pending_dl100["device_type"],
                        CONF_TRANSPORT: TRANSPORT_DLKLAP,
                        CONF_SESSION: latest_session,
                    },
                )

        return self.async_show_form(
            step_id="dl100_session",
            data_schema=DL100_RETRY_SCHEMA,
            errors=errors,
            description_placeholders={"path": import_path},
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
            self.config_entry.options.get(
                CONF_POLL_INTERVAL,
                default,
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
