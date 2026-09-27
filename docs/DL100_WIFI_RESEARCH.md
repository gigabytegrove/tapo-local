# DL100 Wi-Fi reverse-engineering plan

DL100 is a required, release-blocking device for TP-Link Local.

The engineering target is **authorized local Wi-Fi control with no TP-Link account authentication, no cloud API call, and no Internet requirement at runtime or setup**.

## What is already known

The current public DLKLAP research establishes:

- Local transport is plain HTTP on TCP/80.
- Device family: `SMART.TAPOLOCK`.
- Encryption type: `DLKLAP`.
- Login version: `2`.
- A documented working DLKLAP session uses:
  - account login
  - local `handshake0`
  - cloud control-key minting
  - local `handshake1` / `handshake2`
  - encrypted local requests
- Once a session exists, lock status/control requests are local.
- A previously established encrypted session can be restored by another controller without immediately contacting the cloud.

That last point is useful research evidence, but **one-time cloud provisioning is not the final TP-Link Local design**.

## Verified live findings

Validated against a real DL100 hardware 1.0 / firmware 1.0.17 Build 260417 Rel.082002:

- Targeted local TDP exposes lock state, battery state, owner hash, DLKLAP scheme, and other runtime metadata without authentication.
- TCP 80 is the only local control port observed; 443 and 9999 are closed/refused.
- Generic GET/HEAD/OPTIONS requests to known DLKLAP paths return the same canned HTML 200 response and do not expose a conventional REST surface.
- A previously authorized DLKLAP LAN session can be restored by a new controller process and continue making encrypted local requests without a new cloud login.
- A prior HTTP 403 was traced to stale sequence persistence in the research probe, not session expiration.
- Read-only encrypted calls succeeded for `getComponentList`, `getInheritInfo`, `getDeviceRunningInfo`, `getWifiModeStatus`, and `getLockStatus`.
- `getDeviceRunningInfo` returned the especially interesting flags:
  - `switch_appkey: true`
  - `switch_appkey_confirm: false`
  - `cloud_proxy: false`
  - `switch_record_tocloud: false`
- The device advertises first-class components including `security_settings`, `iot_cloud`, `digital_code`, `lock`, and `lock_status`.

The `switch_appkey` fields are now the highest-priority lead. Existing public DL100 reverse-engineering notes also mention Tapo Android classes named `DoorLockLocalControlKeyUtils` and owner raw-key derivation in `DoorLockRepository`, but the decompiled implementations were not published.

## Primary research question

Can a DL100 establish or recover equivalent authorized Wi-Fi session material **entirely locally**?

Potential sources to investigate:

1. Persistent device-side key material.
2. Persistent app-side key/session material.
3. A local provisioning endpoint not used by the current public DLKLAP implementation.
4. A derivation shared with Bluetooth Local Mode.
5. A long-lived authorization artifact established during normal ownership/setup.
6. A local owner credential distinct from the TP-Link cloud account.

## Research rules

- Do not brute-force credentials, codes, tokens, or keys.
- Do not attempt authentication bypass against devices that are not ours.
- Prefer read-only commands until protocol behavior is understood.
- Do not log PIN/user-code material.
- Redact device IDs, MAC addresses, account IDs, SSIDs, and precise location data from shared captures.
- Keep lock/unlock testing separate from protocol discovery.

## Experiment A: unauthenticated Wi-Fi surface

Run:

```bash
python3 tools/dl100_wifi_research.py 172.20.0.100
```

This gathers:

- targeted TDP response
- TCP 80/443/9999 reachability
- HEAD/GET/OPTIONS behavior on known local paths

It does not authenticate and does not change lock state.

## Experiment B: official Tapo app offline matrix

This is the highest-value experiment.

Start with the phone and DL100 on networks that can reach one another locally. Disable cellular data on the phone so there is no accidental mobile fallback.

Test these states in order:

| Test | Phone Internet | DL100 Internet | App restarted? | Goal |
|---|---|---|---|---|
| B1 | allowed | allowed | no | baseline |
| B2 | blocked | allowed | no | does app need direct cloud access? |
| B3 | allowed | blocked | no | does lock need direct cloud access? |
| B4 | blocked | blocked | no | can the current app session operate purely LAN? |
| B5 | blocked | blocked | yes | is authorization persisted in app storage? |
| B6 | blocked | blocked | yes, phone rebooted | is local authorization durable on phone? |

For each test, use **status refresh only first**. Record whether the app displays fresh lock state and how quickly.

If B5/B6 succeeds, the app almost certainly has persistent local authorization material worth reproducing.

A later controlled lock reboot/power test can distinguish app-persistent material from lock-RAM session state.

## Experiment C: packet capture

Capture the phone's Tapo traffic while performing the B-tests.

What matters most:

- Does the phone connect directly to `DL100_IP:80`?
- Which local paths are used?
- Does `handshake0` occur?
- Are `handshake1` / `handshake2` used without a preceding cloud request?
- Which remote TP-Link hosts are contacted before a successful local session?
- Does behavior change after app restart?

The local DLKLAP payload is encrypted, but path, timing, TCP flow, cookies/headers, and cloud-vs-LAN ordering are still valuable.

## Experiment D: Tapo APK static analysis

The current Android package is `com.tplink.iot`.

The most valuable artifact is the exact installed APK/app bundle from the phone that successfully controls the lock. Search/decompile for:

- `DLKLAP`
- `handshake0`
- `handshake1`
- `control-key`
- `SMART.TAPOLOCK`
- `setLockStatus`
- `getLockStatus`
- `getWifiModeStatus`
- `proxyCloud`
- `accessInfo`
- `controlKey`
- any lock-specific local credential/key-store classes

The goal is not to bypass ownership checks. The goal is to determine whether the official app already stores/derives an authorized local Wi-Fi credential that the public DLKLAP implementation missed.

## Experiment E: safe authenticated surface

If using a previously authorized research session, limit initial method calls to read-only methods:

- `getComponentList`
- `getDeviceInfo`
- `getDeviceRunningInfo`
- `getWifiModeStatus`
- `getLockStatus`

Do not query user-code lists or write configuration during discovery.

## Success criteria

DL100 Wi-Fi support is considered solved only when TP-Link Local can, after a fresh Home Assistant start:

1. identify the owned DL100 locally;
2. establish authorized session material without TP-Link cloud/account authentication;
3. read current lock state locally;
4. lock/unlock locally;
5. recover after HA restart and normal session expiry without Internet.

