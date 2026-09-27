# TP-Link Local

A Home Assistant custom integration for **local-first TP-Link/Kasa/Tapo control** with deterministic protocol selection.

TP-Link Local uses **python-kasa as an internal protocol engine**, while keeping its own Home Assistant config flow, device/entity behavior, and connection policy.

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

## Runtime architecture

```text
Home Assistant
      |
      v
TP-Link Local
      |
      +-- owns config flow
      +-- owns entities
      +-- owns protocol-selection policy
      |
      v
python-kasa 0.10.2
      |
      +-- forced DeviceConfig
      +-- no UDP discovery
      +-- no try-all transport selection
      |
      v
KS200 / KS200M TCP/9999 XOR
```

There is no helper daemon, sidecar container, subprocess, or separately managed python-kasa installation. Home Assistant installs the pinned package from the integration manifest.

## Current hardware status

| Model | Backend | Forced transport | Status |
|---|---|---|---|
| KS200 (US) hardware 1.0 | python-kasa 0.10.2 | IOT/XOR TCP 9999 | Supported |
| KS200M (US) hardware 1.0 | python-kasa 0.10.2 | IOT/XOR TCP 9999 | Supported |
| Tapo DL100 | — | — | Not yet supported under strict local-only policy |

## KS200

- Relay on/off through python-kasa
- Relay state
- Status LED through python-kasa `Led` module
- Wi-Fi RSSI
- On-time
- Direct local polling

## KS200M

python-kasa already has first-class support for the device's local PIR modules. TP-Link Local consumes those modules instead of maintaining a parallel implementation.

- Relay on/off
- Motion binary sensor
- PIR enable/disable
- PIR range
- PIR ADC diagnostic sensor
- Calculated PIR percentage
- Status LED
- RSSI / on-time

The underlying python-kasa module is `Module.IotMotion` / `smartlife.iot.PIR`.

## DL100

Released python-kasa **0.10.2 does not include DL100/DLKLAP support**.

An upstream DL100 pull request exists, but its DLKLAP transport explicitly requires TP-Link account authentication and a cloud-issued per-session control key. TP-Link Local will not adopt that transport while this project's requirement is no-account/no-cloud local control.

The DL100 is therefore identified locally but not configured by this build.

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
```

which is also the version currently used by Home Assistant's built-in TP-Link integration.

## VLANs

Supported switches are addressed directly. Broadcast discovery is not required.

Home Assistant needs routed access to TCP port `9999` on KS200/KS200M devices.

## Local-only policy

For supported devices:

- No TP-Link account credentials
- No TP-Link cloud API
- No Internet requirement
- No cloud fallback
- No generic `try_all_connect`
- No protocol guessing
- Direct device IP control

## python-kasa relationship

TP-Link Local depends on python-kasa but is not the Home Assistant built-in TP-Link integration.

The key difference is **connection policy**: TP-Link Local explicitly selects the transport that has been verified on the device instead of asking python-kasa to discover/guess the connection type.

python-kasa is licensed GPL-3.0-or-later and remains a separately installed dependency. See `THIRD_PARTY.md`.

## License

TP-Link Local source is currently Apache License 2.0. See `THIRD_PARTY.md` for dependency licensing.
