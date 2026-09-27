"""Native DLKLAP transport for the TP-Link Tapo DL100.

Device identification and normal lock control are local. Current DL100 firmware
requires a TP-Link-issued control key to provision a DLKLAP session. TP-Link
Local stores that control key and normal runtime never silently falls back to
cloud provisioning.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import http.client
import json
import secrets
import ssl
from typing import Any
from urllib.parse import urlencode, urlsplit
import uuid

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .protocol import (
    TPLinkLocalConnectionError,
    TPLinkLocalDeviceError,
    TPLinkLocalError,
)

CLOUD_LOGIN_URL = "https://wap.tplinkcloud.com/"
CONTROL_KEY_URL_TEMPLATE = (
    "https://use1-app-server.iot.i.tplinknbu.com/v1/things/{device_id}/control-key"
)
SESSION_COOKIE_NAME = "TP_SESSIONID"

DEFAULT_TIMEOUT = 15.0
HANDSHAKE0_RETRIES = 4
HANDSHAKE0_RETRY_DELAY = 1.0


class DlklapAuthenticationError(TPLinkLocalError):
    """DLKLAP authentication failed."""


class DlklapProtocolError(TPLinkLocalError):
    """DLKLAP framing or handshake failed."""


def _sha256(*parts: bytes) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.digest()


def _safe_cloud_error(raw: bytes) -> str:
    """Return a redacted cloud error description without tokens or secrets."""
    try:
        value = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        text = raw.decode("utf-8", errors="replace").strip()
        return text[:300] if text else "<empty response>"

    if not isinstance(value, dict):
        return str(value)[:300]

    safe = {}
    for key in ("error_code", "code", "msg", "message"):
        if key in value:
            safe[key] = value[key]
    return json.dumps(safe or {"response": "unrecognized error body"})


def _pkcs7_pad(data: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    return padder.update(data) + padder.finalize()


def _pkcs7_unpad(data: bytes) -> bytes:
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(data) + unpadder.finalize()


def _extract_json_object(data: bytes) -> dict[str, Any]:
    """Extract the first complete JSON object from a decrypted DLKLAP body."""
    start = data.find(b"{")
    if start < 0:
        raise DlklapProtocolError("DLKLAP response did not contain JSON")

    text = data[start:].decode("utf-8")
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                value = json.loads(text[: index + 1])
                if not isinstance(value, dict):
                    raise DlklapProtocolError("DLKLAP JSON was not an object")
                return value

    raise DlklapProtocolError("DLKLAP response contained incomplete JSON")


def _http_post_sync(
    url: str,
    *,
    body: bytes,
    headers: dict[str, str] | None = None,
    verify_tls: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, str], bytes]:
    """Send a byte-exact HTTP POST."""
    parsed = urlsplit(url)
    request_headers = dict(headers or {})
    request_headers["Content-Length"] = str(len(body))

    if parsed.scheme == "https":
        context = ssl.create_default_context()
        if not verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            parsed.hostname,
            port=parsed.port or 443,
            timeout=timeout,
            context=context,
        )
    elif parsed.scheme == "http":
        connection = http.client.HTTPConnection(
            parsed.hostname,
            port=parsed.port or 80,
            timeout=timeout,
        )
    else:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    try:
        connection.request("POST", path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        response_headers = {
            key.lower(): value for key, value in response.getheaders()
        }
        return response.status, response_headers, payload
    finally:
        connection.close()


async def _http_post(
    url: str,
    *,
    body: bytes,
    headers: dict[str, str] | None = None,
    verify_tls: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, str], bytes]:
    return await asyncio.to_thread(
        _http_post_sync,
        url,
        body=body,
        headers=headers,
        verify_tls=verify_tls,
        timeout=timeout,
    )


class DlklapSession:
    """One live encrypted DLKLAP session."""

    def __init__(self, local_seed: bytes, remote_seed: bytes, lmk: bytes) -> None:
        self.local_seed = local_seed
        self.remote_seed = remote_seed
        self.lmk = lmk
        self.lsk = self._kdf(b"lsk")[:16]
        self.ldk = self._kdf(b"ldk")[:28]
        iv_full = self._kdf(b"iv")
        self.ivb = iv_full[:12]
        self.seq = int.from_bytes(iv_full[28:32], "big") & 0x7FFFFFFF

    def _kdf(self, tag: bytes) -> bytes:
        return _sha256(tag, self.local_seed, self.remote_seed, self.lmk)

    def export_state(self, cookie: str) -> dict[str, Any]:
        """Export the active local session for Home Assistant persistence."""
        return {
            "local_seed": base64.b64encode(self.local_seed).decode("ascii"),
            "remote_seed": base64.b64encode(self.remote_seed).decode("ascii"),
            "lmk": base64.b64encode(self.lmk).decode("ascii"),
            "seq": self.seq,
            "cookie": cookie,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> tuple["DlklapSession", str]:
        """Restore a previously established local session."""
        try:
            local_seed = base64.b64decode(str(state["local_seed"]), validate=True)
            remote_seed = base64.b64decode(str(state["remote_seed"]), validate=True)
            lmk = base64.b64decode(str(state["lmk"]), validate=True)
            seq = int(state["seq"])
            cookie = str(state["cookie"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DlklapProtocolError("Stored DLKLAP session is invalid") from exc
        if len(local_seed) != 16 or len(remote_seed) != 16 or len(lmk) != 32:
            raise DlklapProtocolError("Stored DLKLAP session has invalid key sizes")
        if not cookie.startswith(f"{SESSION_COOKIE_NAME}="):
            raise DlklapProtocolError("Stored DLKLAP session has invalid cookie")
        session = cls(local_seed, remote_seed, lmk)
        session.seq = seq
        return session, cookie

    def encrypt(self, payload: bytes) -> tuple[bytes, int]:
        self.seq += 1
        seq_bytes = self.seq.to_bytes(4, "big")
        iv = self.ivb + seq_bytes

        cipher = Cipher(algorithms.AES(self.lsk), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(_pkcs7_pad(payload)) + encryptor.finalize()
        mac = _sha256(self.ldk, seq_bytes, ciphertext)
        return mac + ciphertext, self.seq

    def decrypt(self, payload: bytes) -> dict[str, Any]:
        if len(payload) < 48:
            raise DlklapProtocolError("DLKLAP encrypted response was too short")

        seq_bytes = self.seq.to_bytes(4, "big")
        iv = self.ivb + seq_bytes
        ciphertext = payload[32:]

        cipher = Cipher(algorithms.AES(self.lsk), modes.CBC(iv))
        decryptor = cipher.decryptor()
        plaintext = _pkcs7_unpad(
            decryptor.update(ciphertext) + decryptor.finalize()
        )
        return _extract_json_object(plaintext)


class Dl100Device:
    """Direct controller for one Tapo DL100."""

    def __init__(
        self,
        host: str,
        *,
        username: str = "",
        password: str = "",
        device_id: str | None = None,
        terminal_uuid: str | None = None,
        control_key: str | None = None,
        session_state: dict[str, Any] | None = None,
        allow_cloud_bootstrap: bool = False,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.device_id = device_id
        self.terminal_uuid = (terminal_uuid or str(uuid.uuid4())).upper()

        self._token: str | None = None
        self._account_id: str | None = None
        self._control_key = control_key
        self._allow_cloud_bootstrap = allow_cloud_bootstrap

        self._cookie: str | None = None
        self._session: DlklapSession | None = None
        self._lock = asyncio.Lock()
        self._last_session_source: str | None = None

        if session_state:
            self._session, self._cookie = DlklapSession.from_state(session_state)
            self._last_session_source = "persisted_session"

    @property
    def control_key(self) -> str | None:
        """Return the provisioned DLKLAP control key."""
        return self._control_key

    def export_session(self) -> dict[str, Any] | None:
        """Return the active encrypted LAN session for persistence."""
        if self._session is None or self._cookie is None:
            return None
        return self._session.export_state(self._cookie)

    @property
    def last_session_source(self) -> str | None:
        """Return how the current/last session was established."""
        return self._last_session_source

    def _local_headers(self, *, with_cookie: bool = False) -> dict[str, str]:
        headers = {
            "Content-Type": "text/plain",
            "Referer": f"http://{self.host}:80/",
            "Accept": "application/json",
            "requestByApp": "true",
        }
        if with_cookie and self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    async def _cloud_login(self) -> None:
        if self._token and self._account_id:
            return

        request = {
            "method": "login",
            "params": {
                "appType": "Tapo_Android",
                "cloudUserName": self.username,
                "cloudPassword": self.password,
                "terminalUUID": self.terminal_uuid,
                "refreshTokenNeeded": False,
            },
        }

        try:
            status, _, raw = await _http_post(
                CLOUD_LOGIN_URL,
                body=json.dumps(request, separators=(",", ":")).encode(),
                headers={"Content-Type": "application/json"},
                verify_tls=True,
            )
        except (OSError, TimeoutError) as exc:
            raise TPLinkLocalConnectionError(
                f"Unable to reach TP-Link provisioning service: {exc}"
            ) from exc

        if status != 200:
            raise TPLinkLocalConnectionError(
                f"TP-Link provisioning login returned HTTP {status}"
            )

        try:
            response = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DlklapProtocolError("Invalid TP-Link login response") from exc

        if response.get("error_code") != 0:
            raise DlklapAuthenticationError(
                f"TP-Link account login failed: {response.get('msg', 'unknown error')}"
            )

        result = response.get("result")
        if not isinstance(result, dict):
            raise DlklapProtocolError("TP-Link login returned no result")

        token = result.get("token")
        account_id = result.get("accountId")
        if not token or not account_id:
            raise DlklapProtocolError("TP-Link login returned no token/accountId")

        self._token = str(token)
        self._account_id = str(account_id)

    async def _resolve_cloud_device_id(self) -> None:
        """Resolve the cloud-side DL100 deviceId during explicit provisioning."""
        if self.device_id:
            return
        if self._token is None:
            raise DlklapProtocolError(
                "DLKLAP cloud token is unavailable for device-id resolution"
            )

        request = {"method": "getDeviceList"}
        try:
            status, _, raw = await _http_post(
                f"{CLOUD_LOGIN_URL}?{urlencode({'token': self._token})}",
                body=json.dumps(request, separators=(",", ":")).encode(),
                headers={"Content-Type": "application/json"},
                verify_tls=True,
            )
        except (OSError, TimeoutError) as exc:
            raise TPLinkLocalConnectionError(
                f"Unable to resolve DL100 cloud device id: {exc}"
            ) from exc

        if status != 200:
            detail = _safe_cloud_error(raw)
            raise TPLinkLocalConnectionError(
                f"DL100 device-list service returned HTTP {status}: {detail}"
            )

        try:
            response = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DlklapProtocolError("Invalid DL100 device-list response") from exc

        if response.get("error_code", 0) != 0:
            raise DlklapAuthenticationError(
                f"DL100 device-list request failed: {_safe_cloud_error(raw)}"
            )

        result = response.get("result")
        devices = result.get("deviceList", []) if isinstance(result, dict) else []
        locks = [
            item
            for item in devices
            if isinstance(item, dict)
            and (
                str(item.get("deviceType", "")) == "SMART.TAPOLOCK"
                or "DL100" in str(item.get("deviceModel", "")).upper()
            )
        ]

        if not locks:
            raise DlklapProtocolError(
                "No DL100 was found in the authenticated TP-Link/Tapo account"
            )
        if len(locks) > 1:
            raise DlklapProtocolError(
                "Multiple DL100 locks were found in the account; "
                "automatic provisioning cannot safely choose one yet"
            )

        cloud_device_id = locks[0].get("deviceId")
        if not cloud_device_id:
            raise DlklapProtocolError(
                "TP-Link device list returned a DL100 without a deviceId"
            )

        self.device_id = str(cloud_device_id)

    async def _handshake0(self, rand4: bytes) -> str:
        if self._account_id is None:
            raise DlklapProtocolError("DLKLAP accountId is unavailable")

        body = _sha256(
            (rand4.hex() + self._account_id).upper().encode("ascii")
        ) + b"\x00"

        last_error: Exception | None = None
        for attempt in range(HANDSHAKE0_RETRIES):
            try:
                status, _, raw = await _http_post(
                    f"http://{self.host}:80/app/handshake0",
                    body=body,
                    headers=self._local_headers(),
                )
                if status == 200:
                    secret = raw.decode().strip()
                    if secret:
                        return secret
                last_error = DlklapProtocolError(
                    f"DLKLAP handshake0 returned HTTP {status}"
                )
            except (OSError, TimeoutError, UnicodeDecodeError) as exc:
                last_error = exc

            if attempt + 1 < HANDSHAKE0_RETRIES:
                await asyncio.sleep(HANDSHAKE0_RETRY_DELAY)

        raise TPLinkLocalConnectionError(
            f"DL100 handshake0 failed: {last_error}"
        )

    async def _fetch_control_key(self, secret: str, rand4: bytes) -> str:
        if self._token is None:
            raise DlklapProtocolError("DLKLAP cloud token is unavailable")
        if not self.device_id:
            raise DlklapProtocolError("DLKLAP cloud deviceId is unavailable")

        headers = {
            "Authorization": f"ut|{self._token}",
            "app-cid": f"app:Tapo_Android:{self.terminal_uuid}",
            "App-Type": "Tapo_Android",
            "x-app-name": "Tapo_Android",
            "UUID": self.terminal_uuid,
            "Terminal-Id": self.terminal_uuid,
            "x-term-id": self.terminal_uuid,
            "Platform": "ANDROID",
            "X-App-Os": "android",
            "Content-Type": "application/json",
        }
        payload = json.dumps(
            {"secret": secret, "random": rand4.hex().upper()},
            separators=(",", ":"),
        ).encode()

        try:
            status, _, raw = await _http_post(
                CONTROL_KEY_URL_TEMPLATE.format(device_id=self.device_id),
                body=payload,
                headers=headers,
                verify_tls=False,
            )
        except (OSError, TimeoutError) as exc:
            raise TPLinkLocalConnectionError(
                f"Unable to obtain DL100 provisioning key: {exc}"
            ) from exc

        if status != 200:
            detail = _safe_cloud_error(raw)
            raise TPLinkLocalConnectionError(
                f"DL100 control-key service returned HTTP {status}: {detail}"
            )

        try:
            response = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DlklapProtocolError("Invalid DL100 control-key response") from exc

        result = response.get("result") or response.get("data") or response
        control_key = result.get("controlKey") if isinstance(result, dict) else None
        if not control_key and isinstance(result, dict):
            control_key = result.get("control_key")
        if not control_key:
            raise DlklapAuthenticationError(
                "DL100 control-key service did not return a control key"
            )
        return str(control_key)

    async def _handshake1(
        self, control_key: str
    ) -> tuple[bytes, bytes, bytes]:
        ck = control_key.upper().encode("ascii")
        lmk = _sha256(ck)
        local_seed = secrets.token_bytes(16)
        body = local_seed + _sha256(local_seed, ck)

        try:
            status, headers, raw = await _http_post(
                f"http://{self.host}:80/app/handshake1",
                body=body,
                headers=self._local_headers(),
            )
        except (OSError, TimeoutError) as exc:
            raise TPLinkLocalConnectionError(
                f"Unable to reach DL100 handshake1: {exc}"
            ) from exc

        if status != 200:
            raise DlklapAuthenticationError(
                f"DLKLAP handshake1 returned HTTP {status}"
            )
        if len(raw) != 48:
            raise DlklapProtocolError(
                f"DLKLAP handshake1 returned {len(raw)} bytes instead of 48"
            )

        remote_seed = raw[:16]
        server_proof = raw[16:]
        expected = _sha256(local_seed, remote_seed, lmk)
        if not hmac.compare_digest(server_proof, expected):
            raise DlklapAuthenticationError(
                "DLKLAP handshake1 server proof did not match"
            )

        cookie = None
        for part in headers.get("set-cookie", "").split(";"):
            part = part.strip()
            if part.startswith(f"{SESSION_COOKIE_NAME}="):
                cookie = part
                break
        if not cookie:
            raise DlklapProtocolError(
                "DLKLAP handshake1 did not return TP_SESSIONID"
            )

        self._cookie = cookie
        return local_seed, remote_seed, lmk

    async def _handshake2(
        self,
        local_seed: bytes,
        remote_seed: bytes,
        lmk: bytes,
    ) -> None:
        try:
            status, _, _ = await _http_post(
                f"http://{self.host}:80/app/handshake2",
                body=_sha256(remote_seed, local_seed, lmk),
                headers=self._local_headers(with_cookie=True),
            )
        except (OSError, TimeoutError) as exc:
            raise TPLinkLocalConnectionError(
                f"Unable to reach DL100 handshake2: {exc}"
            ) from exc

        if status != 200:
            raise DlklapAuthenticationError(
                f"DLKLAP handshake2 returned HTTP {status}"
            )

    async def _establish_session(self) -> None:
        """Provision a fresh session only when explicitly allowed by setup/reconfigure."""
        if not self._allow_cloud_bootstrap:
            raise DlklapAuthenticationError(
                "DL100 local session is unavailable or expired; use Reconfigure "
                "to provision a replacement session"
            )

        await self._cloud_login()
        await self._resolve_cloud_device_id()
        rand4 = secrets.token_bytes(4)
        secret = await self._handshake0(rand4)
        control_key = await self._fetch_control_key(secret, rand4)
        local_seed, remote_seed, lmk = await self._handshake1(control_key)
        await self._handshake2(local_seed, remote_seed, lmk)

        self._control_key = control_key
        self._session = DlklapSession(local_seed, remote_seed, lmk)
        self._last_session_source = "provisioned_session"

    async def _request_once(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        if self._session is None or self._cookie is None:
            raise DlklapProtocolError("DLKLAP session is not established")

        envelope = {
            "method": "multipleRequest",
            "params": {"requests": [request]},
        }
        payload, seq = self._session.encrypt(
            json.dumps(envelope, separators=(",", ":")).encode()
        )

        try:
            status, _, raw = await _http_post(
                f"http://{self.host}:80/app/request?{urlencode({'seq': seq})}",
                body=payload,
                headers=self._local_headers(with_cookie=True),
            )
        except (OSError, TimeoutError) as exc:
            raise TPLinkLocalConnectionError(
                f"Unable to reach DL100 local request endpoint: {exc}"
            ) from exc

        if status == 403:
            raise DlklapAuthenticationError("DLKLAP session was rejected")
        if status != 200:
            raise TPLinkLocalConnectionError(
                f"DL100 returned HTTP {status} for local request"
            )

        response = self._session.decrypt(raw)
        if response.get("error_code", 0) != 0:
            raise TPLinkLocalDeviceError("DL100 request returned an error")

        result = response.get("result")
        responses = result.get("responses") if isinstance(result, dict) else None
        if not isinstance(responses, list) or not responses:
            raise DlklapProtocolError("DL100 response had no nested response")

        item = responses[0]
        if not isinstance(item, dict):
            raise DlklapProtocolError("DL100 nested response was invalid")
        if item.get("error_code", 0) != 0:
            raise TPLinkLocalDeviceError("DL100 command returned an error")

        nested = item.get("result")
        return nested if isinstance(nested, dict) else {}

    async def request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run one command. Runtime never enables cloud provisioning itself."""
        async with self._lock:
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    if self._session is None or self._cookie is None:
                        await self._establish_session()
                    return await self._request_once(request)
                except (
                    DlklapAuthenticationError,
                    DlklapProtocolError,
                    TPLinkLocalConnectionError,
                ) as exc:
                    last_error = exc
                    self._session = None
                    self._cookie = None
                    if attempt == 0:
                        continue
                    raise

            assert last_error is not None
            raise last_error

    async def get_state(self) -> dict[str, Any]:
        info = await self.request({"method": "getDeviceInfo"})
        info.setdefault("model", "DL100")
        info.setdefault("mic_type", "SMART.TAPOLOCK")
        return {"sysinfo": info}

    async def set_lock(self, locked: bool) -> None:
        await self.request(
            {
                "method": "setLockStatus",
                "params": {
                    "lock_status": 0 if locked else 1,
                    "sa_user_id": "local_1",
                },
            }
        )
