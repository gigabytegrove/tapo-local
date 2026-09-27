#!/usr/bin/env python3
"""Read-only DL100 metadata probe using an existing authorized LAN session.

No TP-Link account login, no cloud calls, no handshake0, and no lock/unlock.
The saved sequence number is updated after each successful encrypted request.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_CACHE = Path("/tmp/tapo-dl100-control-key.json")

METHODS = (
    "getComponentList",
    "getInheritInfo",
    "getDeviceRunningInfo",
    "getWifiModeStatus",
    "getLockStatus",
)

REDACT_KEYS = {
    "device_id",
    "deviceId",
    "mac",
    "deviceMac",
    "nickname",
    "ssid",
    "ip",
    "latitude",
    "longitude",
    "longitude_i",
    "latitude_i",
    "username",
    "user_id",
    "accountId",
    "email",
    "token",
    "accessInfo",
    "controlKey",
}


class SessionError(Exception):
    pass


def sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for part in parts:
        h.update(part)
    return h.digest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if key in REDACT_KEYS else redact(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def unpad(data: bytes) -> bytes:
    u = padding.PKCS7(128).unpadder()
    return u.update(data) + u.finalize()


def pad(data: bytes) -> bytes:
    p = padding.PKCS7(128).padder()
    return p.update(data) + p.finalize()


def extract_json(data: bytes) -> dict[str, Any]:
    start = data.find(b"{")
    if start < 0:
        raise SessionError("decrypted response contains no JSON object")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(data[start:].decode("utf-8"))
    if not isinstance(obj, dict):
        raise SessionError("decrypted response is not a JSON object")
    return obj


class SavedSession:
    def __init__(self, state: dict[str, Any]) -> None:
        try:
            self.local_seed = base64.b64decode(state["local_seed"], validate=True)
            self.remote_seed = base64.b64decode(state["remote_seed"], validate=True)
            self.lmk = base64.b64decode(state["lmk"], validate=True)
            self.seq = int(state["seq"])
            self.cookie = str(state["cookie"])
        except Exception as exc:
            raise SessionError(f"invalid saved session: {exc}") from exc

        if len(self.local_seed) != 16 or len(self.remote_seed) != 16 or len(self.lmk) != 32:
            raise SessionError("saved session has invalid seed/key lengths")
        if not self.cookie.startswith("TP_SESSIONID="):
            raise SessionError("saved session cookie is invalid")

        self.lsk = self._kdf(b"lsk")[:16]
        self.ldk = self._kdf(b"ldk")[:28]
        iv = self._kdf(b"iv")
        self.ivb = iv[:12]

    def _kdf(self, tag: bytes) -> bytes:
        return sha256(tag, self.local_seed, self.remote_seed, self.lmk)

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

        enc = Cipher(algorithms.AES(self.lsk), modes.CBC(iv)).encryptor()
        ciphertext = enc.update(pad(plaintext)) + enc.finalize()
        mac = sha256(self.ldk, seq_bytes, ciphertext)
        return mac + ciphertext, self.seq

    def decrypt(self, body: bytes) -> dict[str, Any]:
        if len(body) < 48:
            raise SessionError(f"encrypted response too short: {len(body)} bytes")

        seq_bytes = self.seq.to_bytes(4, "big")
        iv = self.ivb + seq_bytes
        dec = Cipher(algorithms.AES(self.lsk), modes.CBC(iv)).decryptor()
        plaintext = unpad(dec.update(body[32:]) + dec.finalize())
        return extract_json(plaintext)


def request(host: str, session: SavedSession, method: str) -> dict[str, Any]:
    envelope = {
        "method": "multipleRequest",
        "params": {"requests": [{"method": method}]},
    }
    body, seq = session.encrypt(envelope)

    conn = http.client.HTTPConnection(host, 80, timeout=5)
    try:
        conn.request(
            "POST",
            f"/app/request?{urlencode({'seq': seq})}",
            body=body,
            headers={
                "Content-Type": "text/plain",
                "Referer": f"http://{host}:80/",
                "Accept": "application/json",
                "requestByApp": "true",
                "Cookie": session.cookie,
            },
        )
        response = conn.getresponse()
        raw = response.read()
    finally:
        conn.close()

    if response.status == 403:
        raise SessionError("saved DLKLAP session was rejected (HTTP 403)")
    if response.status != 200:
        raise SessionError(f"lock returned HTTP {response.status}")

    decoded = session.decrypt(raw)
    result = decoded.get("result")
    responses = result.get("responses") if isinstance(result, dict) else None
    if not isinstance(responses, list) or not responses:
        raise SessionError(f"{method}: missing nested response")

    item = responses[0]
    if not isinstance(item, dict):
        raise SessionError(f"{method}: invalid nested response")

    return {
        "error_code": item.get("error_code"),
        "result": item.get("result"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="DL100 LAN IP/hostname")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    if not args.cache.exists():
        raise SystemExit(f"Saved session cache not found: {args.cache}")

    cache = json.loads(args.cache.read_text())
    state = cache.get("session")
    if not isinstance(state, dict):
        raise SystemExit("Cache does not contain a saved DLKLAP session")

    session = SavedSession(state)

    print("DL100 SAVED-SESSION METADATA PROBE")
    print("=" * 72)
    print("LOCAL ONLY / READ ONLY")
    print("No cloud authentication. No lock/unlock. No handshake0.\n")

    for method in METHODS:
        print(method)
        print("-" * 72)
        try:
            result = request(args.host, session, method)
            print(json.dumps(redact(result), indent=2, sort_keys=True))
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            if "403" in str(exc):
                break
        finally:
            cache["session"] = session.export()
            args.cache.write_text(json.dumps(cache, indent=2))
            args.cache.chmod(0o600)
        print()

    print(f"Updated saved sequence in {args.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
