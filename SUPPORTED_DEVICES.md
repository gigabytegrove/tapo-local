# Supported devices

TAPO Local is **capability-driven**. It does not maintain a brittle model whitelist for normal python-kasa devices.

A device is accepted when its locally detected protocol family and python-kasa device type map to a Home Assistant platform TAPO Local implements.

This document separates:

- **TAPO Local hardware verified** — physically tested directly with this project.
- **python-kasa 0.10.2 upstream tested** — models represented by python-kasa 0.10.2 fixtures/support and handled by TAPO Local's implemented local transport/platform path.
- **Not yet advertised** — python-kasa may support the device, but TAPO Local does not yet provide the correct Home Assistant platform.

## TAPO Local hardware verified

| Model | Class | Transport | Status |
|---|---|---|---|
| KS200 | wall switch | IOT/XOR TCP 9999 | Verified |
| KS200M | motion wall switch | IOT/XOR TCP 9999 | Verified |
| DL100 | smart lock | DLKLAP HTTP 80 | Verified, including physical lock/unlock |

## Legacy Kasa IOT / XOR

TAPO Local explicitly connects the legacy IOT/XOR transport and lets python-kasa specialize the device from local sysinfo.

Supported Home Assistant classes include plug, wall switch, dimmer, power strip/outlet children, bulb, and light strip.

Known python-kasa 0.10.2 fixture models in this path include:

### Plugs, outlets, switches, dimmers, and strips

- EP10
- EP25 legacy revisions
- EP40
- ES20M
- HS100
- HS103
- HS105
- HS107
- HS110
- HS200 legacy revisions
- HS210
- HS220 legacy revisions
- HS300
- KP100
- KP105
- KP115
- KP125
- KP200
- KP303
- KP400
- KP401
- KP405
- KS200
- KS200M
- KS220
- KS220M
- KS230

Multi-outlet devices are expanded into individual Home Assistant child devices/entities when python-kasa exposes child sockets.

### Bulbs and light strips

- LB100
- LB110
- LB130
- KL110
- KL110B
- KL120
- KL125
- KL130
- KL135
- KL50
- KL60
- KL400L5
- KL400L10
- KL420L5
- KL430

Bulbs, light strips, and dimmers are exposed as native Home Assistant light entities rather than generic number/switch controls.

## Modern Kasa/Tapo SMART devices

TAPO Local performs targeted local TDP discovery, preserves the device-advertised family/encryption settings, and connects through python-kasa using the exact AES/KLAP parameters.

Initial local authentication may require the TP-Link account credentials authorized for the device. Plaintext credentials are not retained after setup.

### Supported SMART families

~~~text
SMART.KASAPLUG
SMART.KASASWITCH
SMART.KASAHUB
SMART.TAPOPLUG
SMART.TAPOBULB
SMART.TAPOSWITCH
SMART.TAPOHUB
~~~

### Known upstream-tested plugs, outlets, and power strips

- EP25 newer SMART revisions
- EP40M
- KP125M
- P100
- P105
- P110
- P110M
- P115
- P125M
- P135
- P210M
- P300
- P304M
- P306
- P316M
- TP15
- TP25

### Known upstream-tested wall switches, dimmers, and fan controls

- HS200 newer SMART revisions
- HS220 newer SMART revisions
- KS205
- KS225
- KS240
- S500
- S500D
- S505
- S505D
- S515D
- TS15

KS240-style fan control is exposed as a native Home Assistant fan entity. Light capability on multifunction devices is exposed separately as a light entity when python-kasa provides it.

### Known upstream-tested bulbs and light strips

- L430C
- L430P
- L510B
- L510E
- L530B
- L530E
- L530EA
- L535E
- L630
- L900-5
- L900-10
- L920-5
- L930-5

Supported capabilities are mapped to native light controls for on/off, brightness, color temperature, and HS color when the device exposes them.

## Hubs and hub-connected sensors

TAPO Local supports python-kasa SMART hub devices as local parent devices and maps supported children as Home Assistant child devices.

Known upstream-tested hubs:

- H100
- KH100
- H200

Known upstream-tested sensor children TAPO Local can map:

- T100 motion sensor
- T110 contact sensor
- T300 water leak sensor
- T310 temperature/humidity sensor
- T315 temperature/humidity sensor
- S210/S220 child switch capabilities when exposed by the hub

Typical child mappings include:

| Child capability | Home Assistant mapping |
|---|---|
| motion_detected | binary_sensor / motion |
| is_open | binary_sensor / opening |
| water_alert | binary_sensor / moisture |
| battery_low | binary_sensor / battery |
| battery_level | sensor / battery |
| temperature | sensor / temperature |
| humidity | sensor / humidity |

### Hub limitations

- S200B/S200D live button-press event streams are not advertised yet because python-kasa 0.10.2 does not provide the event behavior TAPO Local needs.
- KE100 thermostat/climate control is not advertised until TAPO Local implements a proper Home Assistant climate platform.
- H200 camera/video functions are not advertised; the hub/sensor path does not imply camera streaming support.

## Tapo DL100

The DL100 uses TAPO Local's native DLKLAP backend rather than python-kasa 0.10.2.

Current verified behavior:

- local getLockStatus
- local getDeviceRunningInfo
- Home Assistant lock entity
- physical lock
- physical unlock
- post-write state verification
- battery sensor
- low-battery binary sensor
- persistent private DLKLAP session storage

Initial setup currently requires an already-authorized local DLKLAP session import.

## Not yet advertised

TAPO Local intentionally does not claim first-class support for these categories yet, even where python-kasa can communicate with some models:

- cameras
- doorbells
- robot vacuums
- thermostats / climate devices
- button-event remotes requiring live event delivery

Those need dedicated Home Assistant platform behavior before they are considered supported by TAPO Local.

## Firmware and hardware revisions

TP-Link has shipped the same retail model name with different protocol generations.

For example, one hardware revision can use legacy XOR while a later revision uses SMART AES/KLAP.

TAPO Local therefore selects support by **locally detected transport family and capability**, not model name alone.

A model appearing in this document means TAPO Local has a compatible implementation path for the upstream-tested class/revision. It does not mean every firmware ever shipped under that retail model has been physically tested by the TAPO Local project.
