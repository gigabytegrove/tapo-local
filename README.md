<p align="center">
  <a href="https://github.com/gigabytegrove/tapo-local">
    <img src="https://raw.githubusercontent.com/gigabytegrove/tapo-local/main/custom_components/tapo_local/brand/logo.png" alt="Tapo Local logo" width="520">
  </a>
</p>

<h1 align="center">Tapo Local</h1>
<p align="center">Control supported TP-Link Kasa and Tapo devices from Home Assistant, mostly over your home network.</p>

<p align="center">
  <a href="https://github.com/gigabytegrove/tapo-local"><img alt="GitHub repository" src="https://img.shields.io/badge/GitHub-Repository-181717?logo=github&logoColor=white"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/gigabytegrove/tapo-local?label=Stars"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/forks"><img alt="GitHub forks" src="https://img.shields.io/github/forks/gigabytegrove/tapo-local?label=Forks"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/gigabytegrove/tapo-local?label=Issues"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/releases/latest"><img alt="Latest public release" src="https://img.shields.io/github/v/release/gigabytegrove/tapo-local?label=Release"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/blob/main/LICENSE"><img alt="Apache 2.0 license" src="https://img.shields.io/github/license/gigabytegrove/tapo-local?label=License"></a>
  <a href="https://paypal.me/gigabytegrove"><img alt="Support on PayPal" src="https://img.shields.io/badge/Support-PayPal-0070BA?logo=paypal&logoColor=white"></a>
</p>
<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=gigabytegrove&repository=tapo-local&category=integration"><img alt="Add repository to HACS" src="https://my.home-assistant.io/badges/hacs_repository.svg"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/actions/workflows/validate.yml?query=branch%3Amain"><img alt="Main branch validation" src="https://github.com/gigabytegrove/tapo-local/actions/workflows/validate.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/gigabytegrove/tapo-local/actions/workflows/repository-health.yml?query=branch%3Amain"><img alt="Main branch repository health" src="https://github.com/gigabytegrove/tapo-local/actions/workflows/repository-health.yml/badge.svg?branch=main"></a>
</p>

**Useful links:** [Install](#install-with-hacs) · [Supported devices](SUPPORTED_DEVICES.md) · [Recent release notes](CHANGELOG.md) · [Report a problem](https://github.com/gigabytegrove/tapo-local/issues) · [Help and support](SUPPORT.md) · [Source code](https://github.com/gigabytegrove/tapo-local) · [Support development](https://paypal.me/gigabytegrove)

> **Before you begin:** Tapo Local is a community-made Home Assistant integration, not an official TP-Link product. It supports specific device types, not every device sold under the Kasa or Tapo names. Most controls work directly on your network; the **Tapo DL100 smart lock needs your Tapo owner's account for initial setup and to renew an expired encrypted session**. See [DL100 information](#tapo-dl100-smart-locks) before adding a lock.

## What can I use it for?

You can add compatible smart switches, plugs, lights, fans, and sensors to Home Assistant. Supported locks appear as normal Home Assistant lock entities. Your Home Assistant automations can then use those entities.

The device model and firmware matter. See the [supported-device list](SUPPORTED_DEVICES.md) for models and what has actually been tested with this integration. A model listed as supported by the underlying python-kasa library is **not** the same as a model tested here on physical hardware.

## Install with HACS

**HACS is the recommended way to install and update Tapo Local.** You need [Home Assistant](https://www.home-assistant.io/) and [HACS](https://www.hacs.xyz/) installed first.

1. In Home Assistant, open **HACS**.
2. Open HACS's **three-dot menu** and select **Custom repositories**.
3. Enter \`https://github.com/gigabytegrove/tapo-local\` as the repository address.
4. Select **Integration** as the category and add the repository.
5. Find **Tapo Local** in HACS and select **Download**.
6. **Restart Home Assistant** to load the integration.
7. Go to **Settings → Devices & services → Add integration**.
8. Search for **Tapo Local** and open it.
9. Choose [automatic discovery](#find-devices-automatically) or [manual setup](#add-a-device-by-ip-address).

You can also use the [Add to HACS badge](https://my.home-assistant.io/redirect/hacs_repository/?owner=gigabytegrove&repository=tapo-local&category=integration) above to open the repository in Home Assistant.

### Install without HACS

1. Open the [latest public release](https://github.com/gigabytegrove/tapo-local/releases/latest) on GitHub and download its **Source code (zip)**.
2. Unzip it on your computer.
3. Copy the **entire** \`custom_components/tapo_local\` folder into your Home Assistant configuration folder. The final location inside Home Assistant must be \`/config/custom_components/tapo_local/\`, containing \`manifest.json\` and the other integration files.
4. Restart Home Assistant.
5. Follow steps 7–9 above to add a device.

If you use Home Assistant Container, copy the folder into the host directory mounted as \`/config\` inside the container. Do not copy it into a temporary folder inside a running container.

### Python dependency: no manual installation needed

Home Assistant installs Tapo Local's required \`python-kasa>=0.11.0.1\` dependency automatically from the integration manifest. **Do not run \`pip install\` inside a normal Home Assistant installation.** For a separate developer Python environment, see [Contributing](CONTRIBUTING.md).

## Find devices automatically

1. Go to **Settings → Devices & services → Add integration → Tapo Local**.
2. Leave **Device IP address or hostname** empty.
3. Leave **Network to scan** empty to check the networks Home Assistant can identify on its own.
4. Select **Submit** and let the scan finish.
5. Select a found device. Devices already added to Tapo Local are hidden from the list.

**Devices on a separate VLAN or network?** If Home Assistant cannot find that network automatically, put its **network address in CIDR form** in the **Network to scan** field. For example, \`172.20.0.0/16\` includes the subnet information; **you do not need to enter a subnet mask separately**.

A large network takes longer to scan. A \`/16\` contains 65,534 usable device addresses and can take several minutes. Scanning uses local network discovery requests and checks legacy Kasa devices on TCP port 9999. It does **not** connect your devices to your TP-Link account or add them automatically. Firewalls, sleeping devices, or unsupported protocols may prevent a device from appearing.

## Add a device by IP address

If discovery misses a device, return to **Add integration → Tapo Local** and enter its actual IP address or hostname in **Device IP address or hostname**. Leave the scan field empty. Finish the on-screen steps.

This is often the easiest method for a device on a separate VLAN. Home Assistant must be allowed to reach the device on its local network port. Never guess an IP address: confirm it from your router or the Tapo/Kasa app first.

## Tapo DL100 smart locks

The DL100 is different from a normal Kasa switch.

- **During setup:** Tapo Local asks for the original **owner's** Tapo account credentials. It briefly contacts TP-Link to create an encrypted connection to the lock. A shared account may not have permission to authorize that connection.
- **During normal use:** Home Assistant reads the lock and sends lock/unlock commands over your local network.
- **If the encrypted session expires:** Home Assistant may use the owner's saved credentials to contact TP-Link again and renew it automatically. The credentials and session material are stored privately by Home Assistant.
- **If you have two or more DL100s:** Tapo Local checks the locks registered to the owner account. When it cannot match the new lock by its identity, it asks you to select the correct lock by its name and the end of its device ID. **Do not choose a different lock just to get past setup.**
- **If a DL100 is already working:** Do not delete or add it again. Leave that entry in place.

A working DL100 still depends on TP-Link's authorization service whenever a **new** encrypted session is needed. We do not claim that session creation works without the cloud, or that every firmware/version has been tested on real hardware.

### Fix DL100 setup errors

| What Home Assistant says | What to try |
|---|---|
| Owner-account login failed | Check the owner's Tapo email/password and that Home Assistant can reach TP-Link's services. |
| Cannot identify the lock | Make sure you are using the owner account. When asked, select the actual lock you are adding. |
| Control key not issued | Look at the Tapo Local message in **Settings → System → Logs**. If a numeric error code is shown, include that **code only** in a bug report; never post a token, password, or full cloud response. |
| Control key rejected (15033) | This can mean an owner-account or handshake mismatch. Check that you selected the correct lock and did not set up an existing lock a second time. |
| Lock cannot be reached | Check its IP address, that it is awake, and that Home Assistant can reach TCP port 80 on the lock's network. |

**Please do not factory-reset or remove a working lock just to retry authorization.** See [How to get help](#get-help) for what to report safely.

## Change a device's IP address

If your router changes a device's IP address, you do **not** have to remove it from Home Assistant.

1. Open **Settings → Devices & services → Tapo Local**.
2. Find the entry for that device, open its menu, and select **Reconfigure**.
3. Enter the new IP address and submit.
4. Tapo Local checks the device's identity before saving the change. If the device cannot be verified, the old address stays in place.

This is also the right way to move an existing DL100 to a new address. Your existing entities and automations should keep their identities because you are editing the same entry, not starting over.

### Why are there several sections on the integration page?

Home Assistant shows **one entry for each device** because that is how Tapo Local currently saves device configurations. For example, three switches and a lock appear under the same Tapo Local integration, but each has its own entry section. **This is expected in the current version.** Combining them would require a separate tested migration; deleting entries to make the page tidier could break entity history and lock sessions.

## Update Tapo Local

1. In HACS, open **Tapo Local** and install the available update.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Tapo Local** to check the integration version and your existing entries.

Keep your working configuration entries. If you installed manually, replace only the \`custom_components/tapo_local\` code with the files from the latest release, then restart Home Assistant. Make a Home Assistant backup before changing integrations, particularly when you have a working smart-lock session.

## Supported device types

| Type | What Home Assistant can show |
|---|---|
| Compatible plugs and wall switches | On/off switches |
| Compatible bulbs, strips, and dimmers | Light controls |
| Supported fan controls | Fan controls |
| Supported hubs and child sensors | Motion, contact, leak, temperature, humidity and battery information |
| Tapo DL100 | Lock control, lock status and battery information |

The currently documented hands-on test models are **KS200, KS200M, and DL100**. Support for other devices depends on their hardware revision, local communication protocol, and which features Tapo Local can map into Home Assistant. See the [full device list](SUPPORTED_DEVICES.md).

**Not currently offered as first-class platforms:** cameras, video doorbells, robot vacuums, thermostat/climate control, and live button-press events from S200B/S200D.

## Privacy and network use

- Normal device status and control commands travel directly between Home Assistant and your devices.
- Local discovery does not send your login details to scanned devices.
- Supported modern SMART devices authenticate locally; their reusable password-derived protocol data is stored privately, not the plaintext password.
- **DL100 exception:** the owner's credentials are retained privately because that lock needs TP-Link cloud access when a new encrypted session must be authorized.
- Tapo Local does not use a cloud-control fallback for normal device commands.
- Use your router/firewall to permit Home Assistant to reach only the device networks and local ports it needs.

For maintainers: the original Home Assistant integration domain is \`tapo_local\`, and it remains unchanged for upgrades. The underlying device protocols and architecture are documented in [Supported devices](SUPPORTED_DEVICES.md) and the source code. Third-party dependencies and licensing are in [THIRD_PARTY.md](THIRD_PARTY.md).

## Get help

**Something isn't working?** Check [SUPPORT.md](SUPPORT.md) for a short checklist, then [open a GitHub issue](https://github.com/gigabytegrove/tapo-local/issues/new/choose). Include the Tapo Local version, Home Assistant version, exact device model, and what you did before the error.

**Do not post** passwords, authorization tokens, DL100 session files, HomeKit setup codes, device IDs, serial numbers, or unredacted Home Assistant diagnostic exports. If you are unsure, report the visible error and numeric code first.

Feature suggestions and code contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) for the correct channels.

## Development and releases

- **\`dev\` is the only branch for ongoing work.** Changes, documentation updates, and tests belong there.
- **\`main\` is the public release branch.** Work reaches \`main\` through a reviewed pull request from \`dev\` after validation.
- Public version numbers come from \`custom_components/tapo_local/manifest.json\`. A documentation-only edit on \`dev\` does not change that version or create a new release.
- Read the [changelog](CHANGELOG.md) for what changed, and use [GitHub Releases](https://github.com/gigabytegrove/tapo-local/releases) for public versions. Development commits are not advertised as installed releases.

This is an open-source project maintained by **Gigabyte Grove**. The original project author is **Brad Trammell**.

## License and support

Tapo Local is licensed under [Apache License 2.0](LICENSE). It uses separately licensed third-party packages described in [THIRD_PARTY.md](THIRD_PARTY.md).

If Tapo Local is useful to you, [support Gigabyte Grove on PayPal](https://paypal.me/gigabytegrove). Donations are optional and are not required to install or use it.
