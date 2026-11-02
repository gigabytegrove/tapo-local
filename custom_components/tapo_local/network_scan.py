"""Credential-free, opt-in discovery across private IPv4 CIDRs.

Single-shot scans never persist devices or request credentials. CIDR scans send
rate-limited legacy XOR and TDP probes directly to each usable IPv4 host, so
routed VLANs need only the normal UDP firewall rules, not broadcast forwarding.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import socket
from collections.abc import Callable, Iterable
from typing import Any

from .const import SUPPORTED_LEGACY_DEVICE_TYPES, SUPPORTED_SMART_FAMILIES
from .discovery import _build_tdp_packet

_LOGGER = logging.getLogger(__name__)
DEFAULT_DISCOVERY_TARGET = "255.255.255.255"
BROADCAST_SCAN_SECONDS = 4.0
MAX_CIDR_ADDRESSES = 65536
MAX_CANDIDATES = 512
MAX_RESPONSES = 4096
HOSTS_PER_SECOND = 256
HOST_BATCH_SIZE = 32
REPLY_GRACE_SECONDS = 3.0

_PRIVATE_NETWORKS = tuple(
    ipaddress.IPv4Network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_LEGACY_REQUEST = b'{"system":{"get_sysinfo":{}}}'


def validate_discovery_target(target: str) -> str:
    """Accept a single private IPv4 address or at most one private /16."""
    if not isinstance(target, str) or not target.strip():
        raise ValueError("Enter an IPv4 address or private CIDR")
    target = target.strip()
    if target == DEFAULT_DISCOVERY_TARGET:
        return target
    if "/" in target:
        try:
            network = ipaddress.IPv4Network(target, strict=False)
        except ValueError as exc:
            raise ValueError("Enter a valid IPv4 CIDR network") from exc
        if network.num_addresses > MAX_CIDR_ADDRESSES:
            raise ValueError("CIDR ranges larger than /16 are not supported")
        if not any(network.subnet_of(private) for private in _PRIVATE_NETWORKS):
            raise ValueError("Only RFC1918 private IPv4 networks may be scanned")
        return str(network)
    try:
        address = ipaddress.IPv4Address(target)
    except ValueError as exc:
        raise ValueError("Enter a valid IPv4 address or CIDR") from exc
    if not any(address in private for private in _PRIVATE_NETWORKS):
        raise ValueError("Only RFC1918 private IPv4 addresses may be scanned")
    return str(address)


def _xor_encrypt(data: bytes) -> bytes:
    key = 171
    out = bytearray()
    for value in data:
        cipher = value ^ key
        out.append(cipher)
        key = cipher
    return bytes(out)


def _xor_decrypt(data: bytes) -> bytes:
    key = 171
    out = bytearray()
    for cipher in data:
        plain = cipher ^ key
        out.append(plain)
        key = cipher
    return bytes(out)


def _candidate_from_packet(
    payload: bytes, source_port: int, host: str
) -> dict[str, str] | None:
    """Return a supported device's advertised identity, never authorization data."""
    if not 0 < len(payload) <= 65535:
        return None
    try:
        if source_port in (20002, 20004):
            if len(payload) < 17 or payload[0] != 2:
                return None
            envelope = json.loads(payload[16:].decode("utf-8"))
            identity = envelope.get("result") if isinstance(envelope, dict) else None
            if not isinstance(identity, dict):
                return None
            family = str(identity.get("device_type") or "")
            if family not in SUPPORTED_SMART_FAMILIES and family != "SMART.TAPOLOCK":
                return None
            model = str(identity.get("device_model") or "").split("(", 1)[0].strip()
            if family == "SMART.TAPOLOCK" and model != "DL100":
                return None
            if not model:
                return None
            return {
                "host": host,
                "model": model,
                "alias": str(identity.get("nickname") or identity.get("alias") or model),
                "device_id": str(identity.get("device_id") or identity.get("deviceId") or ""),
                "device_type": family,
            }
        if source_port != 9999:
            return None
        for raw in (payload, payload[4:] if len(payload) > 4 else b""):
            try:
                envelope = json.loads(_xor_decrypt(raw).decode("utf-8"))
            except (UnicodeError, ValueError):
                continue
            system = envelope.get("system") if isinstance(envelope, dict) else None
            info = system.get("get_sysinfo") if isinstance(system, dict) else None
            if not isinstance(info, dict):
                continue
            model = str(info.get("model") or "").split("(", 1)[0].strip()
            dtype = str(info.get("type") or "")
            if not model or not (
                dtype.startswith("IOT.") or dtype in SUPPORTED_LEGACY_DEVICE_TYPES
            ):
                continue
            return {
                "host": host,
                "model": model,
                "alias": str(info.get("alias") or model),
                "device_id": str(info.get("deviceId") or info.get("device_id") or ""),
                "device_type": dtype,
            }
    except (UnicodeError, ValueError, TypeError, AttributeError):
        return None
    return None


def _allowed_source(host: str, target: str) -> bool:
    """Discard replies unrelated to the requested private network."""
    try:
        address = ipaddress.IPv4Address(host)
        if not any(address in private for private in _PRIVATE_NETWORKS):
            return False
        if target == DEFAULT_DISCOVERY_TARGET:
            return True
        if "/" in target:
            return address in ipaddress.IPv4Network(target)
        return host == target
    except ValueError:
        return False


async def _listen(
    sock: socket.socket,
    target: str,
    discovered: dict[str, dict[str, str]],
    finished: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    packets = 0
    while not finished.is_set() and packets < MAX_RESPONSES:
        try:
            packet, (host, port) = await asyncio.wait_for(
                loop.sock_recvfrom(sock, 65535), timeout=0.3
            )
        except TimeoutError:
            continue
        except OSError as exc:
            _LOGGER.debug("Discovery receiver stopped: %s", exc)
            return
        packets += 1
        if host in discovered or not _allowed_source(host, target):
            continue
        candidate = _candidate_from_packet(packet, port, host)
        if candidate is not None and len(discovered) < MAX_CANDIDATES:
            discovered[host] = candidate


async def _tcp_probe_legacy(
    host: str, *, timeout: float = 0.45
) -> dict[str, str] | None:
    """Probe legacy Kasa TCP/9999 where UDP discovery is disabled.

    Require a valid framed XOR get_sysinfo response before accepting a host.
    Connections are bounded and discarded immediately after a read-only query.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 9999), timeout=timeout
        )
    except (OSError, TimeoutError):
        return None
    try:
        encrypted = _xor_encrypt(_LEGACY_REQUEST)
        writer.write(len(encrypted).to_bytes(4, "big") + encrypted)
        await asyncio.wait_for(writer.drain(), timeout)
        raw_length = await asyncio.wait_for(reader.readexactly(4), timeout)
        length = int.from_bytes(raw_length, "big")
        if not 0 < length <= 65535:
            return None
        packet = await asyncio.wait_for(reader.readexactly(length), timeout)
        return _candidate_from_packet(packet, 9999, host)
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        return None
    finally:
        writer.close()
        with contextlib.suppress(OSError, TimeoutError):
            await asyncio.wait_for(writer.wait_closed(), timeout)


async def _send(
    sock: socket.socket, host: str, probes: tuple[tuple[int, bytes], ...]
) -> int:
    loop = asyncio.get_running_loop()
    sent = 0
    for port, packet in probes:
        try:
            await loop.sock_sendto(sock, packet, (host, port))
            sent += 1
        except OSError as exc:
            _LOGGER.debug("Discovery UDP send to %s:%s failed: %s", host, port, exc)
    return sent


async def async_scan_local_devices(
    target: str = DEFAULT_DISCOVERY_TARGET,
    *,
    progress_callback: Callable[[float], Any] | None = None,
) -> list[dict[str, str]]:
    """Scan an approved CIDR incrementally without materializing 65k tasks.

    One nonblocking UDP socket is used for all packets. Sending is capped at
    256 hosts/second in batches; a /16 can take several minutes. Replies are
    collected concurrently and a brief grace period follows the last probe.
    """
    validated = validate_discovery_target(target)
    if "/" in validated:
        network = ipaddress.IPv4Network(validated)
        targets = network.hosts()
        total = network.num_addresses - (2 if network.prefixlen <= 30 else 0)
        broadcast_target = str(network.broadcast_address) if network.prefixlen < 31 else None
    else:
        targets = iter((validated,))
        total = 1
        broadcast_target = validated
    probes = (
        (9999, _xor_encrypt(_LEGACY_REQUEST)),
        (20002, _build_tdp_packet()),
        (20004, _build_tdp_packet()),
    )
    discovered: dict[str, dict[str, str]] = {}
    finished = asyncio.Event()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    try:
        sock.bind(("0.0.0.0", 0))
        reader = asyncio.create_task(_listen(sock, validated, discovered, finished))
        try:
            sent = 0
            if broadcast_target:
                sent += await _send(sock, broadcast_target, probes)
                if validated == DEFAULT_DISCOVERY_TARGET:
                    await asyncio.sleep(BROADCAST_SCAN_SECONDS / 2)
                    sent += await _send(sock, broadcast_target, probes)
                    await asyncio.sleep(BROADCAST_SCAN_SECONDS / 2)
                    if progress_callback:
                        progress_callback(1.0)
                    if not sent:
                        raise OSError("Unable to send UDP discovery packets")
                    return sorted(discovered.values(), key=lambda x: (x["model"], x["host"]))

            pending: set[asyncio.Task[dict[str, str] | None]] = set()
            async def collect(tasks: Iterable[asyncio.Task[dict[str, str] | None]]) -> None:
                for task in tasks:
                    candidate = task.result()
                    if candidate and len(discovered) < MAX_CANDIDATES:
                        discovered.setdefault(candidate["host"], candidate)

            try:
                for index, host in enumerate(targets, start=1):
                    address = str(host)
                    sent += await _send(sock, address, probes)
                    if address != broadcast_target and address not in discovered:
                        pending.add(asyncio.create_task(_tcp_probe_legacy(address)))
                    if len(pending) >= 64:
                        done, pending = await asyncio.wait(
                            pending, return_when=asyncio.FIRST_COMPLETED
                        )
                        await collect(done)
                    if index % HOST_BATCH_SIZE == 0:
                        if progress_callback:
                            progress_callback(min(0.98, 0.98 * index / total))
                        await asyncio.sleep(HOST_BATCH_SIZE / HOSTS_PER_SECOND)
                if pending:
                    done, pending = await asyncio.wait(pending)
                    await collect(done)
            finally:
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            if not sent:
                raise OSError("Unable to send UDP discovery packets")
            if progress_callback:
                progress_callback(0.98)
            await asyncio.sleep(REPLY_GRACE_SECONDS)
            if progress_callback:
                progress_callback(1.0)
            return sorted(discovered.values(), key=lambda x: (x["model"], x["host"]))
        finally:
            finished.set()
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
    finally:
        sock.close()


async def async_detect_local_targets(hass: Any) -> list[str]:
    """Respect Home Assistant's enabled network interfaces and their real masks.

    A routed VLAN not present on any HA interface cannot be inferred safely:
    enter that VLAN's CIDR explicitly instead of inventing a network prefix.
    """
    from homeassistant.components import network

    adapters = await network.async_get_adapters(hass)
    candidates: list[tuple[bool, str]] = []
    seen: set[str] = set()
    for adapter in adapters:
        if not adapter.get("enabled"):
            continue
        for info in adapter.get("ipv4", []):
            try:
                target = validate_discovery_target(
                    f"{info['address']}/{int(info['network_prefix'])}"
                )
            except (ValueError, KeyError, TypeError):
                continue
            if target not in seen:
                candidates.append((bool(adapter.get("default")), target))
                seen.add(target)
    # A passive fallback is preferable to guessing a /16 from one host.
    candidates.sort(key=lambda x: (not x[0], x[1]))
    return [target for _, target in candidates[:3]] or [DEFAULT_DISCOVERY_TARGET]


async def async_scan_selected_networks(
    hass: Any,
    target: str = "",
    *,
    progress_callback: Callable[[float], Any] | None = None,
) -> list[dict[str, str]]:
    """Auto-detect the HA adapter CIDRs or scan an explicitly supplied CIDR."""
    targets = [validate_discovery_target(target)] if target.strip() else (
        await async_detect_local_targets(hass)
    )
    by_host: dict[str, dict[str, str]] = {}
    for index, subnet in enumerate(targets):
        def report(progress: float, *, _index: int = index) -> None:
            if progress_callback:
                progress_callback((_index + progress) / len(targets))
        for item in await async_scan_local_devices(
            subnet, progress_callback=report
        ):
            by_host[item["host"]] = item
    return sorted(by_host.values(), key=lambda x: (x["model"], x["host"]))
