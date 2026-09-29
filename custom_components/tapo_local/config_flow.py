"""Config flow for TP-Link Local."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.importlib import async_import_module

from .const import (
    CONF_CREDENTIALS_HASH,
    CONF_DEVICE_FAMILY,
    CONF_ENCRYPTION_TYPE,
    CONF_HTTPS,
    CONF_HTTP_PORT,
    CONF_LOGIN_VERSION,
    CONF_POLL_INTERVAL,
    CONF_SESSION,
    CONF_TRANSPORT,
    DEFAULT_LOCK_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DL100_SESSION_IMPORT,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    SUPPORTED_LEGACY_DEVICE_TYPES,
    SUPPORTED_SMART_DEVICE_TYPES,
    SUPPORTED_SMART_FAMILIES,
    TRANSPORT_DLKLAP,
    TRANSPORT_SMART,
    TRANSPORT_XOR,
)
from .dependency import TPLinkLocalDependencyError, async_ensure_kasa
from .discovery import async_targeted_tdp_discovery


_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})
SMART_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)
DL100_RETRY_SCHEMA = vol.Schema({})


def _smart_connection_from_discovery(
    discovery: dict[str, Any],
) -> dict[str, Any] | None:
    """Return an explicit supported SMART connection from targeted TDP data."""
    family = str(discovery.get("device_type") or "")
    if family not in SUPPORTED_SMART_FAMILIES:
        return None

    scheme = discovery.get("mgt_encrypt_schm")
    if not isinstance(scheme, dict):
        return None

    encryption = str(scheme.get("encrypt_type") or "").upper()
    if encryption not in {"AES", "KLAP"}:
        return None

    login_version = scheme.get("lv")
    if login_version not in (None, ""):
        try:
            login_version = int(login_version)
        except (TypeError, ValueError):
            return None
    else:
        login_version = None

    http_port = scheme.get("http_port")
    if http_port not in (None, ""):
        try:
            http_port = int(http_port)
        except (TypeError, ValueError):
            return None
    else:
        http_port = None

    return {
        "device_family": family,
        "encryption_type": encryption,
        "login_version": login_version,
        "https": bool(scheme.get("is_support_https", False)),
        "http_port": http_port,
    }


def _read_session_import(path: str) -> dict[str, Any]:
    """Read the one-time DL100 import without importing protocol modules."""
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("DL100 session import must be a JSON object")

    session = payload.get("session")
    if not isinstance(session, dict):
        # Also accept a raw session-only object for manually prepared imports.
        required = {"local_seed", "remote_seed", "lmk", "seq", "cookie"}
        if required.issubset(payload):
            session = payload
        else:
            raise ValueError("DL100 session import contains no session object")

    return {
        "session": session,
        "host": str(payload.get("host") or "").strip() or None,
        "device_id": str(
            payload.get("device_id") or payload.get("deviceId") or ""
        ).strip() or None,
        "terminal_uuid": str(payload.get("terminal_uuid") or "").strip() or None,
    }


def _write_session_import(
    path: str,
    state: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Persist sequence advancement without losing DL100 identity metadata."""
    target = Path(path)
    tmp = target.with_name(f"{target.name}.tmp")
    payload = {
        key: value
        for key, value in metadata.items()
        if key in {"host", "device_id", "terminal_uuid"} and value
    }
    payload["session"] = state
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.chmod(0o600)
    tmp.replace(target)


def _remove_session_import(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _find_saved_dl100_sessions(config_dir: str) -> list[dict[str, Any]]:
    """Find orphaned Tapo Local DL100 private session stores.

    Removing a Home Assistant config entry does not necessarily remove the
    integration's private Store file. Re-add flows can therefore recover the
    previously authorized DLKLAP session instead of forcing a manual import.
    """
    storage_dir = Path(config_dir) / ".storage"
    candidates: list[dict[str, Any]] = []
    required = {"local_seed", "remote_seed", "lmk", "seq", "cookie"}

    for path in sorted(storage_dir.glob(f"{DOMAIN}.dl100_session.*")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        # Home Assistant Store files wrap the integration payload in "data".
        data = payload.get("data")
        if not isinstance(data, dict):
            data = payload

        session = data.get("session") if isinstance(data, dict) else None
        if not isinstance(session, dict) or not required.issubset(session):
            continue

        candidates.append(
            {
                "path": str(path),
                "session": session,
            }
        )

    return candidates


def _remove_saved_session(path: str) -> None:
    """Remove a verified orphaned private session store after migration."""
    Path(path).unlink(missing_ok=True)


class TPLinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TP-Link Local config flow."""

    VERSION = 4

    def __init__(self) -> None:
        self._pending_dl100: dict[str, Any] | None = None
        self._pending_smart: dict[str, Any] | None = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a device by address using deterministic local protocols."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            # If an authorized DL100 session import explicitly belongs to this
            # host, use it before python-kasa/XOR or TDP. The encrypted DLKLAP
            # exchange itself is the authoritative verification.
            import_path = self.hass.config.path(DL100_SESSION_IMPORT)
            import_bundle: dict[str, Any] | None = None
            try:
                import_bundle = await self.hass.async_add_executor_job(
                    _read_session_import, import_path
                )
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                pass

            if (
                import_bundle
                and import_bundle.get("host") == host
                and import_bundle.get("device_id")
            ):
                _LOGGER.info(
                    "Using saved DL100 local-session identity for %s; "
                    "skipping python-kasa/XOR and TDP discovery",
                    host,
                )
                self._pending_dl100 = {
                    "host": host,
                    "model": "DL100",
                    "device_type": "SMART.TAPOLOCK",
                    "device_id": import_bundle["device_id"],
                }
                return await self.async_step_dl100_session()

            try:
                await async_ensure_kasa(self.hass)
            except TPLinkLocalDependencyError:
                errors["base"] = "dependency_unavailable"
            else:
                kasa_module = await async_import_module(
                    self.hass, f"{__package__}.kasa_backend"
                )
                KasaLocalDevice = kasa_module.KasaLocalDevice
                TPLinkLocalBackendError = kasa_module.TPLinkLocalBackendError

                backend = KasaLocalDevice(host)

                try:
                    info = await backend.async_probe()
                except TPLinkLocalBackendError:
                    # A verified DL100 cache created by the repository tooling
                    # contains its original host and stable device_id. Prefer
                    # that explicit local identity over intermittent/sleep-
                    # sensitive TDP discovery, then cryptographically verify the
                    # session in async_step_dl100_session.
                    import_path = self.hass.config.path(DL100_SESSION_IMPORT)
                    import_bundle: dict[str, Any] | None = None
                    try:
                        import_bundle = await self.hass.async_add_executor_job(
                            _read_session_import, import_path
                        )
                    except (FileNotFoundError, ValueError, json.JSONDecodeError):
                        pass

                    if (
                        import_bundle
                        and import_bundle.get("device_id")
                        and (
                            import_bundle.get("host") is None
                            or import_bundle.get("host") == host
                        )
                    ):
                        _LOGGER.info(
                            "DL100 saved-session metadata matches the supplied "
                            "host; verifying the encrypted LAN session directly"
                        )
                        self._pending_dl100 = {
                            "host": host,
                            "model": "DL100",
                            "device_type": "SMART.TAPOLOCK",
                            "device_id": import_bundle["device_id"],
                        }
                        return await self.async_step_dl100_session()

                    discovery = await async_targeted_tdp_discovery(host)
                    if discovery:
                        model = str(discovery.get("device_model") or "")
                        dtype = str(discovery.get("device_type") or "")
                        device_id = str(
                            discovery.get("device_id")
                            or discovery.get("deviceId")
                            or host
                        )
                        if (
                            model.split("(", 1)[0].strip() == "DL100"
                            and dtype == "SMART.TAPOLOCK"
                        ):
                            self._pending_dl100 = {
                                "host": host,
                                "model": model or "DL100",
                                "device_type": dtype,
                                "device_id": device_id,
                            }
                            return await self.async_step_dl100_session()

                        smart_connection = _smart_connection_from_discovery(
                            discovery
                        )
                        if smart_connection is not None:
                            self._pending_smart = {
                                "host": host,
                                "model": model,
                                "device_id": device_id,
                                **smart_connection,
                            }
                            return await self.async_step_smart_credentials()

                        errors["base"] = "unsupported_device"
                    else:
                        errors["base"] = "cannot_connect"
                else:
                    model = str(info["model"])
                    device_type = str(info.get("device_type") or "")
                    if device_type not in SUPPORTED_LEGACY_DEVICE_TYPES:
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
                                "device_type": device_type,
                                CONF_TRANSPORT: TRANSPORT_XOR,
                            },
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_smart_credentials(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Authenticate a modern Kasa/Tapo device locally, then store only its hash."""
        if self._pending_smart is None:
            return self.async_abort(reason="cannot_connect")

        errors: dict[str, str] = {}

        if user_input is not None:
            kasa_module = await async_import_module(
                self.hass, f"{__package__}.kasa_backend"
            )
            KasaLocalDevice = kasa_module.KasaLocalDevice
            TPLinkLocalAuthenticationError = (
                kasa_module.TPLinkLocalAuthenticationError
            )
            TPLinkLocalBackendError = kasa_module.TPLinkLocalBackendError

            pending = self._pending_smart
            backend = KasaLocalDevice(
                pending["host"],
                device_family=pending["device_family"],
                encryption_type=pending["encryption_type"],
                login_version=pending.get("login_version"),
                https=bool(pending.get("https", False)),
                http_port=pending.get("http_port"),
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )

            try:
                info = await backend.async_probe()
            except TPLinkLocalAuthenticationError:
                errors["base"] = "invalid_auth"
            except TPLinkLocalBackendError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception(
                    "Unexpected local SMART verification failure for %s",
                    pending["host"],
                )
                errors["base"] = "unknown"
            else:
                device_type = str(info.get("device_type") or "")
                credentials_hash = info.get("credentials_hash")
                if device_type not in SUPPORTED_SMART_DEVICE_TYPES:
                    errors["base"] = "unsupported_device"
                elif not credentials_hash:
                    errors["base"] = "credentials_hash_unavailable"
                else:
                    unique_id = str(
                        info.get("device_id")
                        or pending.get("device_id")
                        or pending["host"]
                    )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: pending["host"]}
                    )

                    data = {
                        CONF_HOST: pending["host"],
                        "model": str(info.get("model") or pending.get("model") or ""),
                        "device_type": device_type,
                        CONF_TRANSPORT: TRANSPORT_SMART,
                        CONF_DEVICE_FAMILY: pending["device_family"],
                        CONF_ENCRYPTION_TYPE: pending["encryption_type"],
                        CONF_HTTPS: bool(pending.get("https", False)),
                        CONF_CREDENTIALS_HASH: str(credentials_hash),
                    }
                    if pending.get("login_version") is not None:
                        data[CONF_LOGIN_VERSION] = pending["login_version"]
                    if pending.get("http_port") is not None:
                        data[CONF_HTTP_PORT] = pending["http_port"]

                    return self.async_create_entry(
                        title=str(
                            info.get("alias")
                            or info.get("model")
                            or pending.get("model")
                            or "TP-Link device"
                        ),
                        data=data,
                    )

        return self.async_show_form(
            step_id="smart_credentials",
            data_schema=SMART_CREDENTIALS_SCHEMA,
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

        dl100_module = await async_import_module(
            self.hass, f"{__package__}.dl100_backend"
        )
        DL100LocalDevice = dl100_module.DL100LocalDevice
        DL100LocalError = dl100_module.DL100LocalError

        # Prefer the explicit one-time import when present. If it is absent,
        # recover any orphaned private session stores left by an earlier Tapo
        # Local config entry and verify them cryptographically against this lock.
        candidates: list[dict[str, Any]] = []
        import_bundle: dict[str, Any] | None = None
        try:
            import_bundle = await self.hass.async_add_executor_job(
                _read_session_import, import_path
            )
        except FileNotFoundError:
            saved = await self.hass.async_add_executor_job(
                _find_saved_dl100_sessions,
                self.hass.config.config_dir,
            )
            candidates.extend(
                {
                    "source": "saved",
                    "path": item["path"],
                    "session": item["session"],
                }
                for item in saved
            )
        except Exception:
            errors["base"] = "dl100_session_invalid"
        else:
            candidates.append(
                {
                    "source": "import",
                    "path": import_path,
                    "session": import_bundle["session"],
                }
            )

        if not errors and not candidates:
            errors["base"] = "dl100_session_missing"

        last_error: Exception | None = None
        for candidate in candidates:
            async def _save_candidate_session(
                state: dict[str, Any],
                *,
                _candidate: dict[str, Any] = candidate,
            ) -> None:
                if _candidate["source"] == "import" and import_bundle is not None:
                    await self.hass.async_add_executor_job(
                        _write_session_import,
                        import_path,
                        state,
                        import_bundle,
                    )

            device = DL100LocalDevice(
                self._pending_dl100["host"],
                session_state=candidate["session"],
                session_saver=_save_candidate_session,
            )
            try:
                state = await device.get_state()
            except DL100LocalError as exc:
                last_error = exc
                _LOGGER.debug(
                    "DL100 saved-session candidate %s did not verify for %s: %s",
                    candidate["path"],
                    self._pending_dl100["host"],
                    exc,
                )
                continue
            except Exception as exc:
                last_error = exc
                _LOGGER.exception(
                    "Unexpected DL100 local-session verification failure for %s",
                    self._pending_dl100["host"],
                )
                continue

            _LOGGER.info(
                "DL100 local-session verification succeeded for %s using %s",
                self._pending_dl100["host"],
                candidate["source"],
            )
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

            if candidate["source"] == "import":
                await self.hass.async_add_executor_job(
                    _remove_session_import, import_path
                )
            else:
                await self.hass.async_add_executor_job(
                    _remove_saved_session, candidate["path"]
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

        if candidates and not errors:
            _LOGGER.warning(
                "No saved DL100 local session verified for %s: %s",
                self._pending_dl100["host"],
                last_error,
            )
            errors["base"] = "dl100_session_rejected"

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
