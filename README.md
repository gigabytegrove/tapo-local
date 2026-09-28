<p align="center">
  <img src="custom_components/tapo_local/brand/logo.png" alt="TAPO Local" width="520">
</p>

# TAPO Local

TAPO Local is a Home Assistant custom integration for **local-first TP-Link, Kasa, and Tapo devices**.

It is built for people who want direct LAN control, deterministic protocol selection, and clear separation between local device access and TP-Link cloud services.

> Home Assistant integration domain: **tapo_local**. The domain is intentionally unchanged so existing installations upgrade safely.

## What TAPO Local supports

TAPO Local uses two local backends:

- **python-kasa 0.10.2** for supported Kasa/Tapo plugs, switches, dimmers, bulbs, light strips, power strips, fans, hubs, and hub-connected sensors.
- A **native DLKLAP backend** for the Tapo DL100 smart lock.

The integration maps device capabilities into native Home Assistant entities instead of exposing everything as generic controls.

| Device capability | Home Assistant entity |
|---|---|
| Plug / relay / outlet | switch |
| Bulb / dimmer / light strip | light |
| Fan speed | fan |
| Motion / contact / leak / low battery | binary_sensor |
| Temperature / humidity / battery / energy / diagnostics | sensor |
| Choice settings | select |
| Numeric settings | number |
| Actions | button |
| DL100 deadbolt | lock |

Power strips are expanded into **individual child outlet devices/entities**. Hubs are expanded into **child sensor devices/entities**.

See [SUPPORTED_DEVICES.md](SUPPORTED_DEVICES.md) for the current device matrix.

## Hardware verified by this project

These models have been tested directly with TAPO Local hardware:

| Model | Local transport | Verified behavior |
|---|---|---|
| Kasa KS200 | IOT/XOR TCP 9999 | Local relay control, status, LED, diagnostics |
| Kasa KS200M | IOT/XOR TCP 9999 | Local relay control, PIR/motion features, LED, diagnostics |
| Tapo DL100 | DLKLAP HTTP 80 | Local state, battery, lock, unlock, persistent local session |

The DL100 lock/unlock path has been physically verified against real hardware.

## Deterministic connection policy

TAPO Local does not use a generic "try every protocol until something works" runtime.

### Legacy Kasa IOT devices

Older Kasa devices are connected using an explicit local XOR configuration. python-kasa reads the device sysinfo and specializes it into the correct plug, wall-switch, dimmer, strip, bulb, or light-strip implementation.

~~~text
device family: IOT.SMARTPLUGSWITCH
encryption:    XOR
transport:     TCP/9999
~~~

No TP-Link account credentials are required for this path.

### Modern Kasa/Tapo SMART devices

For newer local SMART devices, TAPO Local uses targeted local TDP discovery to read the device-advertised family and encryption parameters. Supported AES/KLAP devices then request the account credentials authorized for that device **during initial setup only**.

Those credentials are used locally against the device. TAPO Local then stores python-kasa's protocol-specific **credential hash** in Home Assistant private storage and removes the hash from the normal config entry after the first successful runtime setup.

TAPO Local does not retain the plaintext password.

Supported SMART families currently include:

~~~text
SMART.KASAPLUG
SMART.KASASWITCH
SMART.KASAHUB
SMART.TAPOPLUG
SMART.TAPOBULB
SMART.TAPOSWITCH
SMART.TAPOHUB
~~~

### Tapo DL100

Released python-kasa 0.10.2 does not include the DL100 DLKLAP lock protocol, so TAPO Local provides its own local backend.

A previously authorized DLKLAP LAN session can be imported once. TAPO Local verifies it against the lock, transfers it into Home Assistant private storage, and removes the one-time import file.

Runtime behavior is local:

- getLockStatus
- getDeviceRunningInfo
- setLockStatus
- persistent DLKLAP sequence handling
- physical lock/unlock state verification

Current limitation: TAPO Local does not yet provision a brand-new DL100 authorization session from scratch. An existing authorized LAN session is required for initial import.

## Home Assistant entity behavior

TAPO Local consumes python-kasa's public Device.features interface and maps features into Home Assistant.

Specialized mappings are used when they provide a better HA experience:

- brightness/color temperature/HSV -> native light
- fan speed -> native fan
- strip outlets -> individual child switch devices
- hub sensors -> child sensor/binary-sensor devices
- KS200M PIR -> motion/configuration entities
- DL100 -> native lock

Additional compatible python-kasa features flow into generic sensor, binary sensor, switch, number, select, and button entities.

## Installation

### HACS custom repository

1. Add https://github.com/gigabytegrove/tapo-local to HACS as a custom **Integration** repository.
2. Install **TAPO Local**.
3. Restart Home Assistant.
4. Go to **Settings -> Devices & services -> Add integration**.
5. Search for **TAPO Local**.
6. Enter the device IP address or hostname.
7. If the device uses an authenticated SMART protocol, TAPO Local will ask for credentials during initial local verification.

No separate python-kasa installation is required.

The manifest pins:

~~~text
python-kasa[speedups]==0.10.2
cryptography>=1.9
~~~

Home Assistant's requirements manager installs and validates those dependencies.

## Local-only policy

TAPO Local is designed around LAN device control.

- Direct device IP/hostname access
- No cloud control fallback
- No generic protocol guessing at runtime
- No helper daemon or sidecar
- No manually managed pip install
- Plaintext TP-Link credentials are not retained
- Credential hashes and DL100 session material are stored privately
- Sensitive session/authentication material is redacted from diagnostics

For authenticated SMART devices, the TP-Link account credentials are used to authenticate **to the local device during setup**. The integration does not use them to perform a TP-Link cloud login.

## Networking

TAPO Local can work across routed VLANs because devices are addressed directly.

| Device family | Typical local transport |
|---|---|
| Legacy Kasa IOT | TCP 9999 XOR |
| Modern Kasa/Tapo SMART | HTTP/HTTPS using device-advertised AES/KLAP parameters |
| Tapo DL100 | HTTP 80 DLKLAP |

Firewalls must permit Home Assistant to reach the device on its required local port.

## Security and privacy

TAPO Local treats device authentication material as sensitive.

- DL100 seeds, LMK, cookies, and sequence state live in Home Assistant private storage after import.
- Modern Kasa/Tapo plaintext credentials are used only for initial local verification.
- The reusable protocol credential hash is moved into Home Assistant private storage.
- Diagnostics redact credential hashes, cookies, keys, seeds, device IDs, MAC addresses, aliases, and location fields.

## Scope and limitations

TAPO Local currently focuses on device classes that map cleanly to Home Assistant local-control entities.

Not yet implemented as first-class platforms:

- Tapo/Kasa cameras
- Tapo doorbells
- robot vacuums
- thermostat/climate devices
- live button-press event streams for S200B/S200D

Those device families may be supported by python-kasa, but TAPO Local does not advertise them until their Home Assistant platform behavior is implemented properly.

## Dependency relationship

TAPO Local depends on [python-kasa](https://github.com/python-kasa/python-kasa) for supported Kasa/Tapo protocol implementations and capability definitions. It is a separate Home Assistant custom integration with its own config flow, storage policy, entity mapping, and deterministic connection rules.

python-kasa is installed as a separate dependency and is not vendored into this repository. See [THIRD_PARTY.md](THIRD_PARTY.md).

## License

TAPO Local source is licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
