# TP-Link Local

A Home Assistant custom integration focused on **local-first TP-Link/Kasa/Tapo control**.

The integration implements its device protocols directly. It does not import or install `python-kasa`, and it never routes normal device commands through TP-Link cloud.

## Why this exists

Some current Kasa firmware advertises modern KLAP authentication while Home Assistant/python-kasa connection selection can fail with `try_all_connect`, even though the device still exposes a working local API.

TP-Link Local chooses the proven local transport for the actual device instead of blindly trying protocol combinations.

## v0.1.0 hardware validated during development

| Model | Transport | Control path |
|---|---|---|
| KS200 (US) hardware 1.0 | Native XOR, TCP/9999 | Fully local |
| KS200M (US) hardware 1.0 | Native XOR, TCP/9999 | Fully local |
| Tapo DL100 | Native DLKLAP, HTTP/80 | Local commands; manufacturer-required cloud-assisted session bootstrap |

### KS200 / KS200M

These devices are controlled directly over the LAN using TP-Link's XOR-framed TCP/9999 protocol.

No TP-Link account is required. No Internet connection is required.

### DL100

The DL100 is also controlled directly over the LAN, but its `DLKLAP` firmware is different from normal KLAP.

The lock requires this session sequence:

1. Local `handshake0` with the lock.
2. TP-Link account authentication and a control-key exchange required by the DL100 firmware.
3. Local `handshake1` / `handshake2`.
4. All normal status and lock/unlock requests go directly between Home Assistant and the DL100 on the LAN.

TP-Link Local obtains the DL100 `deviceId` from **local TDP discovery**, so it does not use TP-Link cloud device discovery.

TP-Link Local persists the **already-established encrypted DLKLAP LAN session** (session cookie, derived seeds, and sequence counter) after the explicit provisioning step. TP-Link account credentials are **not stored for normal runtime**. Home Assistant restarts are designed to resume that saved LAN session directly and never silently contact TP-Link.

### DL100 hardware verification

Verified on a real **DL100 hardware 1.0 / firmware 1.0.17 Build 260417 Rel.082002**:

- Local TDP discovery identified `SMART.TAPOLOCK` + `DLKLAP`.
- Explicit provisioning successfully established a DLKLAP session.
- `getDeviceInfo` succeeded locally.
- A completely new controller instance, with **no account credentials and cloud bootstrap disabled**, restored the persisted encrypted LAN session and successfully ran another local `getDeviceInfo`.
- Verified state included lock status, battery, low-battery state, RSSI, firmware and hardware version.

This proves persisted-session reuse works across controller recreation without another cloud bootstrap. We still need to characterize session lifetime across a full Home Assistant restart, DL100 reboot/power event, long idle periods, and normal Tapo-app use.

If the lock rejects or expires the saved session, the runtime stays local and reports the device unavailable instead of falling back to the cloud. Use **Reconfigure** on the integration to explicitly provision a replacement session.

## Features

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
- PIR range selection: Far, Mid, Near, Custom
- Raw PIR ADC diagnostic sensor
- Calculated PIR signal diagnostic sensor

The PIR state comes from the device's local `smartlife.iot.PIR` API.

### DL100

- Lock
- Unlock
- Locked/unlocked/jammed state
- Battery percentage
- Low-battery binary sensor
- Wi-Fi RSSI
- Local TDP identification
- Native DLKLAP encryption/session handling

## Connection strategy

```text
Manual IP / hostname
        |
        +-- TCP/9999 XOR works?
        |       |
        |       +-- KS200 / KS200M
        |             -> native XOR
        |             -> fully local
        |
        +-- otherwise targeted local TDP
                |
                +-- SMART.TAPOLOCK + DLKLAP
                      |
                      +-- DL100 native DLKLAP
                           local handshake0
                           explicit provisioning bootstrap
                           saved encrypted LAN session
                           local encrypted commands
```

There is no `try_all_connect`.

## Installation

### HACS custom repository

1. Add `https://github.com/gigabytegrove/tapo-local` to HACS as a custom **Integration** repository.
2. Install **TP-Link Local**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**.
5. Search for **TP-Link Local**.
6. Enter the device LAN IP or hostname.

For a DL100, the setup flow will request the TP-Link/Tapo account credentials required by the lock's DLKLAP session bootstrap.

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

Broadcast discovery is not required. The integration uses the address you enter and performs targeted local discovery.

Required access:

- KS200 / KS200M: TCP `9999`
- DL100: UDP `20004` for identification and TCP `80` for control
- DL100 initial provisioning/reprovisioning requires HTTPS access to TP-Link's authentication/control-key endpoints to mint a DLKLAP control key; normal runtime does not silently use those endpoints

## Security

The switch protocol is an unauthenticated LAN protocol, so IoT network segmentation remains important.

DL100 account credentials are used only during the explicit setup/reconfigure provisioning flow and are **not stored** in the Home Assistant config entry for normal runtime. The saved runtime material is the already-established encrypted LAN session. The password is not sent to the lock or to Gigabyte Grove.

The DL100 control-key host currently presents a TP-Link private CA rather than a public WebPKI certificate. TLS verification is therefore disabled **only for that control-key request**, matching the device-verified protocol implementation. The account-login request that carries the password remains normally TLS-verified.

## Project rule

A supported device uses direct LAN commands. TP-Link Local will not silently fall back to cloud device control.

Where a device's own security protocol requires a remote session bootstrap, that dependency is explicit in the setup and documentation rather than hidden.

## License

Apache License 2.0.
