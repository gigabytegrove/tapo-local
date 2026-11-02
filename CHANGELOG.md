# Changelog

Release notes tell you what changed, what to do after updating, and what is still limited. New releases use their matching changelog section as GitHub release notes. [See all public releases](https://github.com/gigabytegrove/tapo-local/releases).

## 0.7.9

### Fixed

- **Adding a second DL100:** The setup screen now finds the locks owned by your Tapo account before requesting a new encrypted connection. It no longer assumes an account contains only one lock.
- When the lock cannot be identified automatically, you can select it by its name and the ending of its device ID.
- Locks already registered in Tapo Local are hidden from the choices. Setup checks the chosen lock again before authorization.

### Upgrade notes

- Update through HACS and restart Home Assistant.
- **Do not delete a working DL100 entry.** Add the second lock using its own IP address and choose the correct lock when prompted.
- Your existing entries, saved local lock sessions, and entity IDs are not migrated or reset.

### Known limitations

- Creating a new DL100 encrypted session still requires TP-Link's owner-account authorization service. Automated tests do not prove that the cloud service accepts every firmware or account.

## 0.7.8

### Fixed

- Blocked setup attempts that would add an already registered lock or switch a second time.
- Added a clearer error for control-key code 15033, which can mean an owner-account mismatch or a handshake challenge that is no longer valid.

### Security

- Checks malformed control-key replies without printing passwords, tokens, or full cloud responses in the logs.

### Upgrade notes

- Keep your existing entries. Use **Reconfigure** if a device's IP address changes.

## 0.7.7

### Added

- Finds Home Assistant's enabled network addresses and subnet masks automatically when the discovery field is empty.
- Lets you scan another private network such as 172.20.0.0/16. You do not enter a subnet mask separately.
- Uses an additional TCP port 9999 check for legacy Kasa switches that do not answer UDP discovery.

### Fixed

- No longer uses a DL100's IP address as a substitute for its TP-Link cloud device ID.
- Makes DL100 errors more specific: login, finding the lock, obtaining a control key, or completing the local encrypted connection.
- Added a brief wake check for sleeping DL100 locks before starting a handshake.

### Known limitations

- Scanning a large network takes several minutes, and router/firewall rules may still block discovery. Enter the device IP address manually when necessary.

## 0.7.6

### Added

- Allowed private IP ranges such as 172.20.0.0/16 in the network discovery field.
- Added scan progress, bounded request rates, and a limit on devices kept from one scan.

### Fixed

- Hides devices that are already configured by their stored address or device ID.
- Keeps manual IP setup available.

## 0.7.5

### Added

- Added on-demand discovery for compatible devices on the local broadcast network.
- Shows found devices by name, model, and IP address, and skips devices already registered.

### Known limitations

- The first broadcast scan could miss devices on separate VLANs. Later releases added CIDR and adapter-based scanning.


## 0.7.4

### DL100 IP changes and expired-session recovery

- Fixed Reconfigure failing permanently when a DL100 rejects an expired saved DLKLAP session at its new IP address.
- Reuse the existing privately saved owner account and authorized device ID to refresh the encrypted LAN session at the **new** address; never attempt cloud provisioning for a simple connection timeout.
- Add a dedicated owner-reauthorization step when credentials were not retained or automatic renewal fails.
- Keep the previous IP and private session untouched if the new device cannot be verified, credentials fail, or the device ID does not match the original entry.
- Recover old in-progress DL100 session-import flows by offering fresh authorized credentials instead of stranding users on a rejected import.
- Expand simulated regressions for expired sessions, missing credentials, failed renewal, mismatched identity, unchanged settings and connection errors.

## 0.7.3

### Reconfiguration and Home Assistant compatibility

- Added a native Reconfigure screen for updating a configured device's IP address or hostname without deleting its Home Assistant entry or recreating entities.
- Preserved polling options, existing local protocol parameters, stored credential hashes, and private DL100 sessions.
- Verified the new device's identity before accepting a changed address; unreachable, unsupported or mismatched devices do not overwrite the original host.
- Added regression coverage for XOR, SMART/KLAP and DL100 address changes, IPv4/IPv6 input, authentication and failed connections.
- Set python-kasa minimum version to 0.11.0.1 for Home Assistant compatibility and future Home Assistant-managed upgrades; removed the redundant explicit cryptography requirement from the manifest.

## 0.7.1

### UI clarification

- Clarified that the Tapo DL100 does not provide a fully local method to create its DLKLAP session.
- The setup UI now explains that the owner account credentials are entered once and stored privately in Home Assistant so the user is not prompted again.
- The UI now explicitly states that normal status, lock, and unlock actions are sent directly from Home Assistant to the lock over the local network.
- The UI also explains that Home Assistant may briefly use the stored credentials in the background if the DL100 later invalidates its session and a fresh session must be created.


## 0.7.0

### DL100 automatic session provisioning

- Replaced the manual-session workflow with automatic DLKLAP provisioning for normal DL100 setup.
- DL100 setup now asks once for the TP-Link/Tapo owner account credentials and creates the authorized session itself.
- Owner credentials, device ID, terminal UUID, and DLKLAP session material are moved into Home Assistant private storage.
- HTTP 403 or an unusable encrypted session automatically triggers one serialized fresh-session provisioning attempt and retries the original operation.
- Normal DL100 status, lock, and unlock traffic remains direct LAN traffic.
- TP-Link cloud access is used only to obtain the token/account information and per-session control key required by the verified DLKLAP protocol.
- A successful fresh setup deletes any legacy manual session-import file left by older releases.


## 0.6.4

### DL100 local recovery

- HTTP 403 now triggers a bounded, LAN-only DLKLAP sequence resynchronization sweep before Tapo Local gives up on the session.
- Sequence probes use exponentially increasing candidates so stale sessions can catch up without thousands of requests.
- Failed network requests and rejected sequence probes are no longer persisted as known-good state.
- Only a response that is accepted by the lock and successfully decrypted is checkpointed.
- No TP-Link cloud account, token, or control-key API is used by this recovery path.


## 0.6.3

### Changed

- Removed the cloud-assisted DL100 authentication path introduced in 0.6.1.
- Tapo Local remains local-only and does not request or store TP-Link/Tapo cloud account credentials.
- DL100 persistent local reauthentication remains a release-blocking issue until a durable local authorization artifact can be derived or recovered without TP-Link cloud access.


## 0.6.0

### DL100 reliability overhaul

- Added native DLKLAP session provisioning for Tapo DL100.
- DL100 setup now accepts the owner Tapo account credentials and creates a fresh authorized session automatically.
- Owner credentials, terminal UUID, device ID, and session material are moved into Home Assistant private storage after setup.
- HTTP 403 and DLKLAP decryption/session failures automatically trigger one serialized fresh-session reauthentication and retry.
- Normal lock/unlock and status requests remain local after the session handshake completes.
- Removed the requirement to manually maintain a session-import JSON file for normal DL100 setup.
- Changed sequence persistence so an uncertain transport failure is not checkpointed as a known-good sequence state.


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
