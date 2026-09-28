# TP-Link Local

A Home Assistant custom integration for **local-first TP-Link/Kasa/Tapo control** with deterministic protocol selection.

TP-Link Local uses **python-kasa as its device capability engine** while keeping its own Home Assistant config flow, device policy, entity model, and connection rules.

## Why this exists

Home Assistant's built-in TP-Link integration also uses python-kasa, but its normal connection flow can attempt multiple transports/protocols when a device advertises newer capabilities.

On the tested KS200/KS200M firmware, the devices advertise modern KLAP while simultaneously exposing a fully working legacy local XOR API on TCP/9999. TP-Link Local does not use `try_all_connect` or automatic transport selection for these devices.

Instead it constructs an explicit python-kasa `DeviceConfig`:

```text
device family: IOT.SMARTPLUGSWITCH
encryption:    XOR
transport:     TCP/9999
host:          manually supplied IP/hostname
```

That forces the proven local path.

## python-kasa integration

TP-Link Local now consumes python-kasa's public `Device.features` interface directly instead of hand-implementing a small subset of module APIs.

At setup time python-kasa initializes the device and its supported modules/features. TP-Link Local then maps those features into Home Assistant entities:

| python-kasa feature type | Home Assistant entity |
|---|---|
| `Switch` | switch |
| `BinarySensor` | binary sensor |
| read-only boolean `Sensor` | binary sensor |
| `Sensor` | sensor |
| `Choice` | select |
| `Number` | number |
| `Action` | button |

This means new features added by python-kasa can flow into Tapo-Local without requiring a new hand-written entity for every setting.

Existing TP-Link Local entity identities for relay, LED, motion, PIR enable/range, RSSI, on-time, PIR ADC and PIR percentage are preserved so upgrades do not intentionally replace the existing entities.

python-kasa remains a normal Home Assistant Python dependency. There is no helper daemon, sidecar container, subprocess, or separately managed python-kasa installation.

## Runtime architecture

```text
Home Assistant
      |
      v
TP-Link Local
      |
      +-- owns config flow / entities
      +-- owns deterministic connection policy
      +-- maps python-kasa Device.features to HA
      |
      v
python-kasa 0.10.2
      |
      +-- device protocol implementation
      +-- modules
      +-- generic feature API
      |
      v
KS200 / KS200M TCP/9999 XOR
```

## Current hardware status

| Model | Backend | Forced transport | Status |
|---|---|---|---|
| KS200 (US) hardware 1.0 | python-kasa 0.10.2 | IOT/XOR TCP 9999 | Supported |
| KS200M (US) hardware 1.0 | python-kasa 0.10.2 | IOT/XOR TCP 9999 | Supported |
| Tapo DL100 | Native local saved-session DLKLAP runtime | HTTP/80 DLKLAP | Supported with an existing authorized LAN session |

## KS200

The KS200 is driven through python-kasa's feature API. Current exposed capabilities include relay state/control, LED configuration, Wi-Fi RSSI, on-time diagnostics, reboot action, and any additional compatible python-kasa features presented by the device.

## KS200M

python-kasa has first-class support for the local `smartlife.iot.PIR` module. Tapo-Local now consumes its feature definitions directly, including:

- relay on/off
- motion state
- PIR enable/disable
- PIR range
- **PIR threshold**
- PIR ADC diagnostics
- calculated PIR percentage
- status LED
- RSSI / on-time
- python-kasa actions and any future feature additions

## DL100

Released python-kasa **0.10.2 does not include DL100/DLKLAP support**, so DL100 uses a separate native local-only backend inside TP-Link Local.

TP-Link Local 0.4.0 can restore and use an **existing authorized DLKLAP LAN session**. This path has no TP-Link account login, cloud API fallback, handshake0 provisioning, or account credentials in runtime.

When a DL100 is identified during setup, TP-Link Local looks for a one-time session import at:

```text
/config/.storage/tapo_local_dl100_session_import.json
```

The import accepts the same saved-session cache format used by the repository's verified `dl100_saved_session_probe.py` tool. The session object contains the encrypted LAN session seeds/key material, current sequence, and `TP_SESSIONID` cookie.

Setup verifies that session directly against the lock. If verification succeeds:

- a Home Assistant `lock` entity is created
- lock/unlock uses local `setLockStatus`
- battery and low-battery entities are exposed
- polling uses local `getDeviceInfo`, `getLockStatus`, and `getDeviceRunningInfo`
- the live DLKLAP sequence is persisted in Home Assistant private storage
- the one-time import file is deleted after successful import

If the saved session is missing, invalid, or rejected, setup reports that specific condition instead of marking DL100 unsupported.

**Current limitation:** TP-Link Local does not yet create a brand-new DL100 authorization session from scratch. A current authorized local session must already exist for the initial import. Runtime after import remains local-only.

## Installation

### HACS custom repository

1. Add `https://github.com/gigabytegrove/tapo-local` to HACS as a custom **Integration** repository.
2. Install **TP-Link Local**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**.
5. Search for **TP-Link Local**.
6. Enter the device IP address or hostname.

No separate python-kasa installation is required. The integration manifest pins:

```text
python-kasa[speedups]==0.10.2
cryptography>=1.9
```

Home Assistant is responsible for installing declared integration requirements. TP-Link Local 0.4.0 also performs its own runtime preflight before any TP-Link device I/O:

1. Check the active Home Assistant Python environment for the required python-kasa version.
2. Ask Home Assistant's requirements manager to install/repair the pinned dependency if it is missing or mismatched.
3. Verify that python-kasa is importable and is the expected version.
4. Only then initialize the device backend.
5. If dependency preparation fails, do not contact or change the TP-Link device; show a clear configuration error and create a **Settings → System → Repairs** issue describing what Home Assistant could not prepare.

Manual `pip install` commands inside Home Assistant are not part of the supported installation process.

## VLANs

Supported switches are addressed directly. Broadcast discovery is not required.

Home Assistant needs routed access to TCP port `9999` on KS200/KS200M devices and TCP port `80` on DL100.

## Local-only policy

For supported devices:

- No TP-Link account credentials
- No TP-Link cloud API
- No Internet requirement
- No cloud fallback
- No generic `try_all_connect`
- No protocol guessing
- Direct device IP control

## Dependency relationship

TP-Link Local depends on python-kasa but is not the Home Assistant built-in TP-Link integration.

The key difference is **connection policy**: Tapo-Local explicitly selects the transport verified for the device while using python-kasa for protocol implementation, modules, and feature definitions.

python-kasa is licensed GPL-3.0-or-later and remains a separately installed dependency. See `THIRD_PARTY.md`.

## License

TP-Link Local source is currently Apache License 2.0. See `THIRD_PARTY.md` for dependency licensing.
