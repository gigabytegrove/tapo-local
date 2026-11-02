"""DL100 cloud-assisted DLKLAP session provisioning.

The DL100 requires TP-Link's cloud only to mint a fresh control key for each
DLKLAP session. After the handshake completes, normal status and lock/unlock
traffic is local to the LAN.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
import socket
import time
import ssl
import uuid
from typing import Any
from urllib.parse import quote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SESSION_COOKIE_NAME = "TP_SESSIONID"


class DL100ProvisioningError(Exception):
    """Fresh DLKLAP session establishment failed, with a safe stage identifier."""

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code


@contextmanager
def _provision_stage(stage: str):
    """Classify failures without exposing tokens, credentials or endpoint URLs."""
    try:
        yield
    except DL100ProvisioningError as exc:
        if not exc.stage:
            exc.stage = stage
        raise
    except (OSError, TimeoutError, http.client.HTTPException, ssl.SSLError) as exc:
        raise DL100ProvisioningError(
            f"{stage} connection failed ({type(exc).__name__})", stage=stage
        ) from exc



def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for part in parts:
        h.update(part)
    return h.digest()


def _request(
    scheme: str,
    host: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    timeout: float = 10.0,
    verify_tls: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    payload = body.encode() if isinstance(body, str) else body
    hdrs = dict(headers or {})
    if payload is not None:
        hdrs["Content-Length"] = str(len(payload))

    if scheme == "https":
        context = ssl.create_default_context()
        if not verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, timeout=timeout, context=context
        )
    else:
        conn = http.client.HTTPConnection(host, timeout=timeout)

    try:
        conn.request("POST", path, body=payload, headers=hdrs)
        response = conn.getresponse()
        response_headers = {k.lower(): v for k, v in response.getheaders()}
        return response.status, response_headers, response.read()
    finally:
        conn.close()


def _wake_lock(host: str, *, timeout: float = 1.0) -> bool:
    """Best-effort DL100 radio wake with no handshake or state mutation.

    The DL100 may initially refuse TCP connections while its Wi-Fi radio
    sleeps. Never retry handshake0 itself: repeating that challenge can
    invalidate a control key already minted for a previous handshake.
    """
    for attempt in range(3):
        try:
            with socket.create_connection((host, 80), timeout=timeout):
                return True
        except OSError:
            if attempt < 2:
                time.sleep(0.3)
    return False


def _cloud_login(
    username: str,
    password: str,
    terminal_uuid: str,
) -> tuple[str, str]:
    body = {
        "method": "login",
        "params": {
            "appType": "Tapo_Android",
            "cloudUserName": username,
            "cloudPassword": password,
            "terminalUUID": terminal_uuid,
            "refreshTokenNeeded": False,
        },
    }
    status, _, raw = _request(
        "https",
        "wap.tplinkcloud.com",
        "/",
        headers={"Content-Type": "application/json"},
        body=json.dumps(body, separators=(",", ":")),
    )
    if status != 200:
        raise DL100ProvisioningError(f"Tapo cloud login returned HTTP {status}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DL100ProvisioningError("Tapo cloud login returned invalid JSON") from exc
    if value.get("error_code") != 0:
        raise DL100ProvisioningError(
            f"Tapo cloud login failed with error_code {value.get('error_code')}"
        )
    result = value.get("result")
    if not isinstance(result, dict) or not result.get("token") or result.get("accountId") is None:
        raise DL100ProvisioningError("Tapo cloud login returned no token/account ID")
    return str(result["token"]), str(result["accountId"])


def _owned_dl100_list(token: str) -> list[dict[str, str]]:
    """List owner-account DL100s without logging tokens, IDs or cloud payloads."""
    status, _, raw = _request(
        "https",
        "wap.tplinkcloud.com",
        f"/?token={quote(token)}",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"method": "getDeviceList"}, separators=(",", ":")),
    )
    if status != 200:
        raise DL100ProvisioningError(
            f"getDeviceList returned HTTP {status}", stage="cloud_device"
        )
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DL100ProvisioningError(
            "getDeviceList returned invalid JSON", stage="cloud_device"
        ) from exc
    if not isinstance(value, dict) or value.get("error_code") != 0:
        code = value.get("error_code") if isinstance(value, dict) else None
        raise DL100ProvisioningError(
            f"getDeviceList failed (error_code {code})", stage="cloud_device"
        )
    result = value.get("result")
    devices = result.get("deviceList") if isinstance(result, dict) else None
    if not isinstance(devices, list):
        raise DL100ProvisioningError(
            "getDeviceList returned no device list", stage="cloud_device"
        )
    found: dict[str, dict[str, str]] = {}
    for item in devices:
        if not isinstance(item, dict):
            continue
        model = str(item.get("deviceModel") or "")
        device_id = str(item.get("deviceId") or "").strip()
        if "DL100" not in model.upper() or not device_id:
            continue
        alias = str(item.get("alias") or item.get("deviceName") or "DL100").strip()
        found[device_id] = {"device_id": device_id, "alias": alias[:90], "model": model}
    return sorted(found.values(), key=lambda x: (x["alias"].casefold(), x["device_id"]))


def list_owned_dl100_devices(username: str, password: str) -> list[dict[str, str]]:
    """Authenticate owner and return the owned locks before any LAN handshake."""
    with _provision_stage("cloud_login"):
        token, _ = _cloud_login(username.strip(), password, str(uuid.uuid4()).upper())
    with _provision_stage("cloud_device"):
        return _owned_dl100_list(token)


def _resolve_device_id(token: str, preferred_device_id: str | None) -> str:
    """Fail closed if an owner account cannot uniquely resolve the lock.

    The config flow resolves multi-lock accounts BEFORE handshake0. Retain
    explicit IDs on future reauthorization, but do not invent one from an IP.
    """
    if preferred_device_id and preferred_device_id not in {"", "None"}:
        try:
            import ipaddress
            ipaddress.ip_address(preferred_device_id)
        except ValueError:
            return preferred_device_id
    found = _owned_dl100_list(token)
    if len(found) != 1:
        raise DL100ProvisioningError(
            "Multiple or no DL100 locks found; select the correct lock from "
            "the owner-account list before starting a session",
            stage="cloud_device",
        )
    return found[0]["device_id"]


def _parse_control_key_response(raw: bytes) -> str:
    """Extract the key without returning or logging sensitive cloud response data.

    TP-Link uses both error_code and code in API failures. A 15033 means
    the owning account did not match the lock's current handshake challenge
    (including a challenge invalidated by another handshake0).
    """
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DL100ProvisioningError(
            "control-key response was not valid JSON", stage="control_key"
        ) from exc
    if not isinstance(payload, dict):
        raise DL100ProvisioningError(
            "control-key response was not an object", stage="control_key"
        )
    item = payload.get("result") or payload.get("data") or payload
    if not isinstance(item, dict):
        raise DL100ProvisioningError(
            "control-key response contained no result", stage="control_key"
        )
    key = item.get("controlKey") or item.get("control_key")
    if isinstance(key, str) and len(key) == 64 and all(
        char in "0123456789abcdefABCDEF" for char in key
    ):
        return key
    code = payload.get("error_code")
    if code is None:
        code = payload.get("code")
    if code is None:
        code = item.get("error_code", item.get("code"))
    try:
        code_int = int(code) if code is not None else None
    except (TypeError, ValueError):
        code_int = None
    if code_int == 15033:
        raise DL100ProvisioningError(
            "DL100 control-key rejected (15033): owner mismatch or superseded "
            "handshake challenge",
            stage="control_key",
            code=15033,
        )
    raise DL100ProvisioningError(
        f"DL100 control-key not issued (error code {code_int if code_int is not None else 'unavailable'})",
        stage="control_key",
        code=code_int,
    )


def establish_session(
    host: str,
    username: str,
    password: str,
    *,
    terminal_uuid: str | None = None,
    device_id: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Establish a fresh owner DLKLAP session and return persistent state."""
    terminal_uuid = (terminal_uuid or str(uuid.uuid4())).upper()
    with _provision_stage("cloud_login"):
        token, account_id = _cloud_login(username.strip(), password, terminal_uuid)
    with _provision_stage("cloud_device"):
        device_id = _resolve_device_id(token, device_id)

    local_headers = {
        "Content-Type": "text/plain",
        "Referer": f"http://{host}:80/",
    }

    # Waking the sleeping radio is safe; handshake0 is NOT retryable.
    _wake_lock(host, timeout=min(float(timeout), 2.0))

    # Handshake 0
    rand4 = os.urandom(4)
    digest_input = (rand4.hex() + account_id).upper().encode("ascii")
    hs0_body = _sha256(digest_input)[:32] + bytes([0])
    with _provision_stage("handshake0"):
        status, _, hs0_raw = _request(
            "http",
            host,
            "/app/handshake0",
            headers=local_headers,
            body=hs0_body,
            timeout=timeout,
        )
        if status != 200:
            raise DL100ProvisioningError(f"DL100 handshake0 returned HTTP {status}")
        secret = hs0_raw.decode("utf-8", errors="strict").strip()
        if not secret:
            raise DL100ProvisioningError("DL100 handshake0 returned no challenge")

    # Cloud control key. TP-Link uses a private CA on this endpoint.
    ck_body = json.dumps(
        {"secret": secret, "random": rand4.hex().upper()},
        separators=(",", ":"),
    )
    with _provision_stage("control_key"):
        status, _, ck_raw = _request(
            "https",
            "use1-app-server.iot.i.tplinknbu.com",
            f"/v1/things/{quote(device_id, safe='')}/control-key",
            headers={
                "Authorization": f"ut|{token}",
                "app-cid": f"app:Tapo_Android:{terminal_uuid}",
                "App-Type": "Tapo_Android",
                "x-app-name": "Tapo_Android",
                "UUID": terminal_uuid,
                "Terminal-Id": terminal_uuid,
                "x-term-id": terminal_uuid,
                "Platform": "ANDROID",
                "X-App-Os": "android",
                "Content-Type": "application/json",
            },
            body=ck_body,
            timeout=timeout,
            verify_tls=False,
        )
        if status != 200:
            raise DL100ProvisioningError(f"control-key endpoint returned HTTP {status}")
        control_key = _parse_control_key_response(ck_raw)

    # Handshake 1
    ck = str(control_key).upper().encode("ascii")
    lmk = _sha256(ck)
    local_seed = os.urandom(16)
    hs1_body = local_seed + _sha256(local_seed, ck)
    with _provision_stage("handshake1"):
        status, hs1_headers, hs1_raw = _request(
            "http",
            host,
            "/app/handshake1",
            headers=local_headers,
            body=hs1_body,
            timeout=timeout,
        )
        if status != 200:
            raise DL100ProvisioningError(f"DL100 handshake1 returned HTTP {status}")
        if len(hs1_raw) < 48:
            raise DL100ProvisioningError("DL100 handshake1 response was too short")

        set_cookie = hs1_headers.get("set-cookie", "")
        cookie = next(
            (
                part.strip()
                for part in set_cookie.split(";")
                if part.strip().startswith(f"{SESSION_COOKIE_NAME}=")
            ),
            None,
        )
        if not cookie:
            raise DL100ProvisioningError("DL100 handshake1 returned no TP_SESSIONID")

        remote_seed = hs1_raw[:16]
        server_proof = hs1_raw[16:48]
        if _sha256(local_seed, remote_seed, lmk) != server_proof:
            raise DL100ProvisioningError("DL100 handshake1 server proof mismatch")

    # Handshake 2
    with _provision_stage("handshake2"):
        status, _, _ = _request(
            "http",
            host,
            "/app/handshake2",
            headers={**local_headers, "Cookie": cookie},
            body=_sha256(remote_seed, local_seed, lmk),
            timeout=timeout,
        )
        if status != 200:
            raise DL100ProvisioningError(f"DL100 handshake2 returned HTTP {status}")

    iv_full = _sha256(b"iv", local_seed, remote_seed, lmk)
    seq = int.from_bytes(iv_full[28:32], "big") & 0x7FFFFFFF

    return {
        "session": {
            "local_seed": base64.b64encode(local_seed).decode("ascii"),
            "remote_seed": base64.b64encode(remote_seed).decode("ascii"),
            "lmk": base64.b64encode(lmk).decode("ascii"),
            "seq": seq,
            "cookie": cookie,
        },
        "terminal_uuid": terminal_uuid,
        "device_id": device_id,
    }
