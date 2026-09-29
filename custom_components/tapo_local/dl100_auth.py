"""DL100 cloud-assisted DLKLAP session provisioning.

The DL100 requires TP-Link's cloud only to mint a fresh control key for each
DLKLAP session. After the handshake completes, normal status and lock/unlock
traffic is local to the LAN.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import ssl
import uuid
from typing import Any
from urllib.parse import quote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SESSION_COOKIE_NAME = "TP_SESSIONID"


class DL100ProvisioningError(Exception):
    """Fresh DLKLAP session establishment failed."""


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


def _resolve_device_id(token: str, preferred_device_id: str | None) -> str:
    if preferred_device_id and preferred_device_id not in {"", "None"}:
        return preferred_device_id

    status, _, raw = _request(
        "https",
        "wap.tplinkcloud.com",
        f"/?token={quote(token)}",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"method": "getDeviceList"}, separators=(",", ":")),
    )
    if status != 200:
        raise DL100ProvisioningError(f"getDeviceList returned HTTP {status}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DL100ProvisioningError("getDeviceList returned invalid JSON") from exc
    if value.get("error_code") != 0:
        raise DL100ProvisioningError(
            f"getDeviceList failed with error_code {value.get('error_code')}"
        )
    devices = (value.get("result") or {}).get("deviceList") or []
    dl100s = [
        item for item in devices
        if isinstance(item, dict) and "DL100" in str(item.get("deviceModel") or "")
    ]
    if len(dl100s) != 1:
        raise DL100ProvisioningError(
            "Unable to uniquely resolve this DL100 from the Tapo account"
        )
    device_id = dl100s[0].get("deviceId")
    if not device_id:
        raise DL100ProvisioningError("Tapo cloud device list returned no DL100 device ID")
    return str(device_id)


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
    token, account_id = _cloud_login(username, password, terminal_uuid)
    device_id = _resolve_device_id(token, device_id)

    local_headers = {
        "Content-Type": "text/plain",
        "Referer": f"http://{host}:80/",
    }

    # Handshake 0
    rand4 = os.urandom(4)
    digest_input = (rand4.hex() + account_id).upper().encode("ascii")
    hs0_body = _sha256(digest_input)[:32] + bytes([0])
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

    # Cloud control key. TP-Link uses a private CA on this endpoint.
    ck_body = json.dumps(
        {"secret": secret, "random": rand4.hex().upper()},
        separators=(",", ":"),
    )
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
    try:
        ck_response = json.loads(ck_raw)
    except json.JSONDecodeError as exc:
        raise DL100ProvisioningError("control-key endpoint returned invalid JSON") from exc
    ck_obj = ck_response.get("result") or ck_response.get("data") or ck_response
    control_key = ck_obj.get("controlKey") or ck_obj.get("control_key")
    if not control_key:
        code = ck_response.get("error_code") or ck_response.get("code")
        raise DL100ProvisioningError(f"control-key missing (code={code})")

    # Handshake 1
    ck = str(control_key).upper().encode("ascii")
    lmk = _sha256(ck)
    local_seed = os.urandom(16)
    hs1_body = local_seed + _sha256(local_seed, ck)
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
