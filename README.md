# TP-Link Local

A Home Assistant custom integration for **strict local-only TP-Link/Kasa/Tapo control**.

The project rule is simple:

> **No TP-Link account authentication, no TP-Link cloud API, and no Internet requirement for device control.**

The integration implements supported device protocols directly and does not import or install `python-kasa`.

## Why this exists

Some current Kasa firmware advertises modern KLAP authentication while Home Assistant/python-kasa connection selection can fail with `try_all_connect`, even when the device still exposes a working local API.

TP-Link Local selects a proven local transport for the actual device rather than blindly trying protocol combinations or falling back to cloud services.

## Current hardware status

| Model | Local transport | Status |
|---|---|---|
| KS200 (US) hardware 1.0 | Native XOR, TCP/9999 | Supported |
| KS200M (US) hardware 1.0 | Native XOR, TCP/9999 | Supported |
| Tapo DL100 | Bluetooth Local Mode | Required support target; BLE transport under development |

### KS200 / KS200M

These devices are controlled directly over the LAN using TP-Link's XOR-framed TCP/9999 protocol.

- No TP-Link account
- No cloud API
- No Internet
- Direct Home Assistant → device LAN traffic

### DL100

The DL100's Wi-Fi protocol is `DLKLAP`. Reverse-engineered DLKLAP session establishment requires TP-Link account authentication and a cloud-issued control key. That does **not** meet this project's local-only requirement, so TP-Link Local does not expose that path.

TP-Link documents a separate **Bluetooth Local Mode** for the DL100 that can set up and control the lock without Wi-Fi or Internet. That is the transport this project will target for DL100 support.

The previous experimental DLKLAP/cloud-bootstrap code has been removed from the Home Assistant runtime component. Its history remains available in Git if protocol research is needed.

## Supported features

### KS200

- Relay on/off
- Relay state
- Status LED control
- Wi-Fi RSSI
- Current on-time
- Direct LAN polling

### KS200M

Everything above, plus:

- Motion binary sensor
- PIR enable/disable
- PIR range selection
- Raw PIR ADC diagnostic sensor
- Calculated PIR signal diagnostic sensor

## Connection strategy

```text
KS200 / KS200M
      |
      +-- TCP 9999
      +-- native XOR
      +-- local LAN only

DL100
      |
      +-- Bluetooth Local Mode
      +-- native BLE transport
      +-- no TP-Link account/cloud
      +-- implementation in progress
```

There is no `try_all_connect` and no cloud fallback.

## Installation

### HACS custom repository

1. Add `https://github.com/gigabytegrove/tapo-local` to HACS as a custom **Integration** repository.
2. Install **TP-Link Local**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**.
5. Search for **TP-Link Local**.
6. Enter the LAN IP/hostname for a supported Kasa switch.

DL100 will not request TP-Link credentials. Until the BLE transport is complete, detecting a DL100 reports that Bluetooth Local Mode support is required rather than offering cloud authentication.

### Manual

Copy:

```text
custom_components/tapo_local/
```

to:

```text
/config/custom_components/tapo_local/
```

and restart Home Assistant.

## VLANs

The supported KS200/KS200M path does not require broadcast discovery. Manual IP/hostname works across routed VLANs as long as Home Assistant can reach TCP port `9999` on the device.

DL100 Bluetooth support will use Home Assistant's Bluetooth stack / supported Bluetooth proxies rather than its Wi-Fi DLKLAP cloud-bootstrap path.

## Security

The classic Kasa TCP/9999 protocol is unauthenticated on the LAN, so network segmentation remains important.

TP-Link Local does not ask for or store TP-Link/Tapo account credentials.

## License

Apache License 2.0.
