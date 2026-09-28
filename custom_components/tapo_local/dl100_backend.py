"""Local-only DLKLAP runtime for Tapo DL100.

This module restores an already-authorized encrypted LAN session. It contains
no TP-Link account login, cloud API, handshake0 provisioning, or credential
fallback. Session material is expected to have been obtained from an authorized
DL100 session and is advanced/persisted as requests are made.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import hashlib
import http.client
import json
from typing import Any
from urllib.parse import urlencode

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SESSION_COOKIE_NAME = "TP_SESSIONID"


class DL100LocalError(Exception):
    """Base DL100 local runtime error."""


class DL100SessionError(DL100LocalError):
    """Saved DLKLAP session is missing, invalid, or rejected."""


class DL100ConnectionError(DL100LocalError):
    """DL100 could not be reached locally."""


def _sha256(*parts: bytes) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.digest()


def _pad(data: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    return padder.update(data) + padder.finalize()


def _unpad(data: bytes) -> bytes:
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(data) + unpadder.finalize()


def _extract_json(data: bytes) -> dict[str, Any]:
    start = data.find(b"{")
    if start < 0:
        raise DL100SessionError("DLKLAP response contained no JSON object")
    try:
        value, _ = json.JSONDecoder().raw_decode(data[start:].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DL100SessionError("DLKLAP response contained invalid JSON") from exc
    if not isinstance(value, dict):
        raise DL100SessionError("DLKLAP response was not a JSON object")
    return value


class DL100LocalSession:
    """Restorable encrypted DLKLAP LAN session."""

    def __init__(
        self,
        local_seed: bytes,
        remote_seed: bytes,
        lmk: bytes,
        seq: int,
        cookie: str,
    ) -> None:
        if len(local_seed) != 16 or len(remote_seed) != 16 or len(lmk) != 32:
            raise DL100SessionError("Saved DLKLAP session has invalid key sizes")
        if seq < 0:
            raise DL100SessionError("Saved DLKLAP sequence is invalid")
        if not cookie.startswith(f"{SESSION_COOKIE_NAME}="):
            raise DL100SessionError("Saved DLKLAP session cookie is invalid")

        self.local_seed = local_seed
        self.remote_seed = remote_seed
        self.lmk = lmk
        self.seq = seq
        self.cookie = cookie

        self.lsk = self._kdf(b"lsk")[:16]
        self.ldk = self._kdf(b"ldk")[:28]
        iv_full = self._kdf(b"iv")
        self.ivb = iv_full[:12]

    def _kdf(self, tag: bytes) -> bytes:
        return _sha256(tag, self.local_seed, self.remote_seed, self.lmk)

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "DL100LocalSession":
        """Restore the exact saved-session format used by the verified probe."""
        try:
            return cls(
                base64.b64decode(str(state["local_seed"]), validate=True),
                base64.b64decode(str(state["remote_seed"]), validate=True),
                base64.b64decode(str(state["lmk"]), validate=True),
                int(state["seq"]),
                str(state["cookie"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DL100SessionError("Saved DLKLAP session is invalid") from exc

    def export(self) -> dict[str, Any]:
        return {
            "local_seed": base64.b64encode(self.local_seed).decode("ascii"),
            "remote_seed": base64.b64encode(self.remote_seed).decode("ascii"),
            "lmk": base64.b64encode(self.lmk).decode("ascii"),
            "seq": self.seq,
            "cookie": self.cookie,
        }

    def encrypt(self, value: dict[str, Any]) -> tuple[bytes, int]:
        self.seq += 1
        seq_bytes = self.seq.to_bytes(4, "big")
        iv = self.ivb + seq_bytes
        plaintext = json.dumps(value, separators=(",", ":")).encode()

        encryptor = Cipher(algorithms.AES(self.lsk), modes.CBC(iv)).encryptor()
        ciphertext = encryptor.update(_pad(plaintext)) + encryptor.finalize()
        mac = _sha256(self.ldk, seq_bytes, ciphertext)
        return mac + ciphertext, self.seq

    def decrypt(self, body: bytes) -> dict[str, Any]:
        if len(body) < 48:
            raise DL100SessionError(
                f"DLKLAP encrypted response was too short ({len(body)} bytes)"
            )

        seq_bytes = self.seq.to_bytes(4, "big")
        iv = self.ivb + seq_bytes
        decryptor = Cipher(
            algorithms.AES(self.lsk), modes.CBC(iv)
        ).decryptor()
        try:
            plaintext = _unpad(
                decryptor.update(body[32:]) + decryptor.finalize()
            )
        except ValueError as exc:
            raise DL100SessionError(
                "DLKLAP response could not be decrypted with the saved session"
            ) from exc
        return _extract_json(plaintext)


def extract_session_state(value: dict[str, Any]) -> dict[str, Any]:
    """Accept either the probe cache wrapper or the raw session object."""
    state = value.get("session") if isinstance(value.get("session"), dict) else value
    if not isinstance(state, dict):
        raise DL100SessionError("Session import does not contain a session object")
    # Validate before returning a normalized copy.
    return DL100LocalSession.from_state(state).export()


SessionSaver = Callable[[dict[str, Any]], Awaitable[None]]


class DL100LocalDevice:
    """Local-only controller for one DL100 using a restored DLKLAP session."""

    def __init__(
        self,
        host: str,
        *,
        session_state: dict[str, Any],
        session_saver: SessionSaver | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.timeout = timeout
        self._session = DL100LocalSession.from_state(session_state)
        self._session_saver = session_saver
        self._request_lock = asyncio.Lock()

    def export_session(self) -> dict[str, Any]:
        return self._session.export()

    async def _persist_session(self) -> None:
        if self._session_saver is not None:
            await self._session_saver(self.export_session())

    def _post_sync(self, body: bytes, seq: int) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection(
            self.host,
            80,
            timeout=self.timeout,
        )
        try:
            connection.request(
                "POST",
                f"/app/request?{urlencode({'seq': seq})}",
                body=body,
                headers={
                    "Content-Type": "text/plain",
                    "Referer": f"http://{self.host}:80/",
                    "Accept": "application/json",
                    "requestByApp": "true",
                    "Cookie": self._session.cookie,
                },
            )
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one encrypted local request and persist the advanced sequence."""
        async with self._request_lock:
            request: dict[str, Any] = {"method": method}
            if params is not None:
                request["params"] = params

            envelope = {
                "method": "multipleRequest",
                "params": {"requests": [request]},
            }
            body, seq = self._session.encrypt(envelope)

            try:
                status, raw = await asyncio.to_thread(self._post_sync, body, seq)
            except (OSError, TimeoutError) as exc:
                raise DL100ConnectionError(
                    f"Unable to reach DL100 {self.host}:80: {exc}"
                ) from exc
            finally:
                # The sequence has advanced whether or not the response was
                # usable. Persist it so a restart never intentionally restores
                # the older sequence used before this request attempt.
                await self._persist_session()

            if status == 403:
                raise DL100SessionError(
                    "DL100 rejected the saved local session (HTTP 403)"
                )
            if status != 200:
                raise DL100ConnectionError(
                    f"DL100 returned HTTP {status} for {method}"
                )

            decoded = self._session.decrypt(raw)
            result = decoded.get("result")
            responses = result.get("responses") if isinstance(result, dict) else None
            if not isinstance(responses, list) or not responses:
                raise DL100SessionError(
                    f"DL100 {method} response had no nested response"
                )

            item = responses[0]
            if not isinstance(item, dict):
                raise DL100SessionError(
                    f"DL100 {method} returned an invalid nested response"
                )
            if item.get("error_code", 0) != 0:
                raise DL100LocalError(
                    f"DL100 {method} returned error_code {item.get('error_code')}"
                )

            nested = item.get("result")
            return nested if isinstance(nested, dict) else {}

    @staticmethod
    def _merge_result(target: dict[str, Any], result: dict[str, Any]) -> None:
        target.update(result)
        for key in ("device_info", "basic_info", "lock_info"):
            nested = result.get(key)
            if isinstance(nested, dict):
                target.update(nested)

    async def get_state(self) -> dict[str, Any]:
        """Read identity, lock state, and running/battery metadata locally."""
        sysinfo: dict[str, Any] = {}
        for method in ("getDeviceInfo", "getLockStatus", "getDeviceRunningInfo"):
            result = await self.request(method)
            self._merge_result(sysinfo, result)

        sysinfo.setdefault("model", "DL100")
        sysinfo.setdefault("mic_type", "SMART.TAPOLOCK")
        return {"sysinfo": sysinfo}

    async def set_lock(self, locked: bool) -> None:
        """Set physical lock state using the proven local_1 service user."""
        await self.request(
            "setLockStatus",
            {
                "lock_status": 0 if locked else 1,
                "sa_user_id": "local_1",
            },
        )
