# Changelog

## 0.5.5

### Fixed

- Re-adding a previously configured DL100 now automatically searches Tapo Local's orphaned private Home Assistant session stores.
- Each recovered DLKLAP session is cryptographically verified against the supplied lock before reuse.
- A verified orphaned session is migrated into the new config entry and the obsolete private store is removed.
- Manual `tapo_local_dl100_session_import.json` is now only required when no reusable prior Tapo Local session exists.


## 0.5.4

### Fixed

- DL100 transient LAN poll failures no longer make the entire device immediately unavailable after a single missed request.
- Tapo Local retains the DL100's last-known-good state for up to two consecutive connection failures, then marks it unavailable on the third consecutive miss.
- DL100 protocol/session failures still mark the device unavailable immediately rather than being masked as transient connectivity.
- Added explicit warning, error, and recovery logging for DL100 local polling so intermittent failures are visible in Home Assistant logs.
- Corrected the coordinator display name to Tapo Local.


## 0.5.3

- Corrected the product name capitalization throughout the repository and Home Assistant metadata from `TAPO Local` to `Tapo Local`.


## 0.5.0

### Added

- Expanded legacy Kasa IOT/XOR support beyond KS200/KS200M to compatible plugs, wall switches, dimmers, power strips, bulbs, and light strips supported by python-kasa 0.10.2.
- Added authenticated local SMART support for supported Kasa/Tapo plug, switch, bulb, and hub families using exact targeted-TDP transport metadata.
- Added one-time local credential verification for SMART devices.
- Added private Home Assistant storage for reusable python-kasa credential hashes; plaintext passwords are not retained.
- Added native Home Assistant light entities for compatible bulbs, light strips, and dimmers.
- Added native Home Assistant fan entities for fan-capable devices such as KS240.
- Added child-device/entity support for multi-outlet power strips.
- Added H100/KH100/H200 hub support with child sensor entity mapping.
- Added motion, contact, water-leak, battery, temperature, and humidity device-class mappings for common hub children.
- Added SUPPORTED_DEVICES.md.

### Changed

- Product branding is now consistently **Tapo Local** in Home Assistant, HACS metadata, and repository documentation.
- Existing integration domain remains tapo_local for upgrade compatibility.
- Device support is capability/transport driven rather than a KS200/KS200M model whitelist.
- Diagnostics now redact credential hashes and DL100 session/authentication material.

### Preserved

- KS200 and KS200M existing behavior and entity identities.
- DL100 local DLKLAP runtime, persistent private session storage, and physically verified lock/unlock support.
- Deterministic local transport policy with no cloud-control fallback.

### Not yet advertised

- Cameras and doorbells
- Robot vacuums
- Thermostat/climate devices
- S200B/S200D live button-press event streams

## 0.4.6

- Added verified DL100 physical lock/unlock write handling with post-command state verification.
- Preserved and advanced the persistent private DLKLAP session sequence.
