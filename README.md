# TP-Link Local

A Home Assistant custom integration for **local-first TP-Link/Kasa control with no Internet required**.

TP-Link Local talks directly to supported devices on your LAN. It does not use TP-Link cloud discovery, cloud control, `python-kasa`, a helper daemon, or a sidecar container.

## Why this exists

Recent Kasa firmware can advertise modern KLAP authentication while some Home Assistant / TP-Link connection paths fail during protocol selection. Supported Kasa switches can also expose the classic local TCP/9999 protocol. TP-Link Local uses the local device protocol directly instead of sending normal control through the cloud or relying on `try_all_connect`.

## v0.1.0 supported hardware

Validated against real devices:

| Model | Local transport | Status |
|---|---|---|
| KS200 (US) hardware 1.0 | Native XOR, TCP/9999 | Supported |
| KS200M (US) hardware 1.0 | Native XOR, TCP/9999 | Supported |
| Tapo DL100 | DLKLAP | Detected but intentionally not controlled |

The DL100 is not controlled in strict local-first mode because its currently documented DLKLAP session bootstrap requires a TP-Link cloud-issued control key. TP-Link Local will not silently introduce that dependency.

## KS200 features

- Relay on/off
- Relay state
- Status LED control
- Wi-Fi RSSI
- Current on-time
- Direct LAN polling

## KS200M features

Everything above, plus:

- Motion binary sensor
- PIR enable/disable
- PIR range selection: Far, Mid, Near, Custom
- Raw PIR ADC diagnostic sensor
- Calculated PIR signal diagnostic sensor

The motion state is calculated from the KS200M's local `smartlife.iot.PIR` `get_config` and `get_adc_value` responses.

## Local-first rules

For supported devices:

- Home Assistant connects to the device IP directly.
- Internet access is not required.
- TP-Link account credentials are not required.
- TP-Link cloud APIs are not contacted.
- Cloud discovery is not used.
- Cloud fallback is not used.
- `python-kasa` is not installed or imported.
- Normal control remains on the LAN.

## Installation

### HACS custom repository

1. Open HACS.
2. Add `https://github.com/gigabytegrove/tapo-local` as a custom **Integration** repository.
3. Install **TP-Link Local**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Search for **TP-Link Local**.
7. Enter the LAN IP address of the switch.

### Manual

Copy:

```text
custom_components/tapo_local/
```

into:

```text
/config/custom_components/tapo_local/
```

and restart Home Assistant.

## VLANs

Automatic broadcast discovery is not required. Add devices by their LAN IP or hostname, so routed VLAN installations work as long as Home Assistant is permitted to reach the device.

For current KS200/KS200M support, Home Assistant must be able to reach TCP port `9999` on the device.

## Architecture

```text
Home Assistant
      |
      | LAN only
      v
TP-Link Local
      |
      +-- native XOR framing
      +-- native TCP socket
      +-- native JSON API
      |
      v
KS200 / KS200M :9999
```

There is no external Python service in this path.

## Security

TP-Link Local never sends your Kasa device state or credentials to Gigabyte Grove. v0.1.0 does not require TP-Link credentials at all.

The classic Kasa TCP/9999 protocol is an unauthenticated LAN protocol. Network segmentation and firewalling remain important: only trusted automation hosts should be allowed to reach IoT device networks.

## Device compatibility policy

A device is only marked supported when there is a complete local control path. A device that requires cloud bootstrap or cloud control will not be represented as fully local.

Future native transports can be added inside the integration without changing that policy.

## License

Apache License 2.0.
