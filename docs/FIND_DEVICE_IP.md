# How to find your Tapo or Kasa device's IP address

If Tapo Local cannot find your device automatically, you can add it using its **IP address**. You do not need to know how networking works to find it.

**Start with the Tapo or Kasa app.** If that does not show the address, look for the device in your router's connected-device list. Matching its **MAC address** can help when the router calls it "Unknown" instead of showing its real name.

> **Already have this device working in Home Assistant?** Do not delete it or add it again. If its address changed, open **Settings → Devices & services → Tapo Local**, select the menu on that device's existing entry, and choose **Reconfigure**. This preserves your entities and, for a DL100, its saved lock session.

## Three things worth knowing

| Term | What it means | Example |
|---|---|---|
| **IP address** | The current address your router gives a device on your home network. This is what you enter in Tapo Local. | `192.168.1.47` or `172.20.0.42` |
| **MAC address** | An identifier for a device's **network connection**. It usually stays the same when its IP address changes. Use it to recognize a device in the router's list. | `02:11:22:33:44:55` |
| **DHCP list / DHCP leases** | The list of IP addresses the router has given out, usually along with device names and MAC addresses. Routers may call this **Connected devices**, **Clients**, or **Attached devices**. | Shows which device currently has `192.168.1.47` |

These addresses are **examples**, not real addresses you should copy. MAC addresses are not passwords, but they can identify your equipment; avoid posting full addresses and router screenshots publicly.

## Method 1: Check the Tapo or Kasa app

This is usually the easiest place to start.

1. Open the **Tapo** or **Kasa** app on your phone.
2. Select the switch, plug, bulb, or lock you want to add to Home Assistant.
3. Open its **Settings** or **Device Settings** screen, usually through a gear icon.
4. Look for **Device Info**, **Device Information**, **About**, or **Network**. App labels vary by device and app version.
5. If the screen shows **IP address**, write it down exactly. You can skip the router steps.
6. If you see **MAC address** or **Wi-Fi MAC**, write that down instead. You'll use it to find the IP address in your router.

Some devices do **not** show their IP or MAC address in the app. That is normal; continue to Method 2.

**For a DL100 smart lock:** Use its **Wi-Fi MAC address** if it is shown. A Bluetooth address or a setup code may not match the Wi-Fi connection listed by your router. Do not remove or factory-reset a working lock to look for its address.

## Method 2: Look in your router's connected-device list

Your **router** is the device or system that manages your home network and usually assigns IP addresses. This might be a box supplied by your Internet provider, a separate Wi-Fi router, or a gateway managed through an app.

1. Open the app you normally use to manage your home Wi-Fi, or sign in to the router's administration page. Use your **router's login**, not your Tapo account.
2. Find a page called **Connected Devices**, **Devices**, **Clients**, **Attached Devices**, **Network Map**, **DHCP Clients**, or **DHCP Leases**.
3. Look for the device's friendly name first, for example **Kitchen Light**, **Tapo**, **Kasa**, **TP-Link**, or the model number.
4. If the name is missing or says **Unknown**, look at the **MAC address** shown for each device. Compare it with the MAC address found in Method 1 or on the device label.
5. Once the MAC addresses match, write down the **IPv4 address** in that **same row**.
6. Enter that IPv4 address in Tapo Local's **Device IP address or hostname** field.

Common places to look (menu wording varies with firmware):

| Router or network system | Look for a page named something like |
|---|---|
| TP-Link / Deco | **Clients**, **Connected Devices**, or **DHCP Client List** |
| TP-Link Omada | **Clients** or the gateway's **DHCP leases** |
| UniFi Network | **Clients** or the gateway's **DHCP** information |
| ASUS | **Network Map → Clients** or **DHCP** |
| NETGEAR | **Attached Devices** |
| eero or an ISP-provided router | **Devices** or **Connected Devices** in the router's app |

You may not see the exact words above. Look for **a list that shows both a device name or MAC address and an IPv4 address**.

### Example: Match the MAC address

Suppose the Tapo app or device label shows this **Wi-Fi MAC address**:

`02:11:22:33:44:55`

Your router might show:

| Name shown in router | MAC address | IPv4 address |
|---|---|---|
| Living Room TV | `02:AA:AA:AA:AA:01` | `192.168.1.25` |
| Unknown | `02-11-22-33-44-55` | `192.168.1.47` |
| Phone | `02:BB:BB:BB:BB:02` | `192.168.1.80` |

The **Unknown** row is the match: `02:11:22:33:44:55` and `02-11-22-33-44-55` are the same address written with different separators.

**Use `192.168.1.47` in Tapo Local.** Do **not** type the MAC address into the IP-address field.

MAC address comparison is not affected by uppercase versus lowercase letters. However, match the **whole address**, not just the first few characters. The printed label and the Wi-Fi connection can sometimes have different MAC addresses; if they do not match, do not choose a random row.

## Method 3: Find your router's login page

If you are not sure where to open the router's device list:

- **On Windows:** Open **Command Prompt**, type `ipconfig`, and look for **Default Gateway** under your active Wi-Fi or Ethernet connection. An address such as `192.168.1.1` is often your router's management address. Enter it in a browser if your router supports a web login.
- **On Android or iPhone:** Open your current **Wi-Fi network details** and look for **Router** or **Gateway**. You may be able to open that address in a browser, or you may need your router's app.
- **For managed networks:** A separate gateway or controller may hold the DHCP list. A Wi-Fi access point does not necessarily assign IP addresses, so its client list may omit them.

**Important:** The **Default Gateway** is usually the *router's* IP, not the Tapo device's IP. Use it only to find the device list. Then copy the Tapo device's address from that list.

Do not change router passwords, firewall rules, or network settings just to view the list.

## Method 4: When your router does not show the device

Try the following in order:

1. **Check that the device is online.** In the Tapo/Kasa app, see whether it currently responds. A powered-off device or a sleeping lock may disappear from the active client list.
2. **Look for an offline or recently seen device list.** DHCP leases can remain listed even while the device is offline. Some routers show old entries for a while, so check whether a device was **recently connected**.
3. **Check the correct Wi-Fi network or VLAN.** Smart-home devices may be on a different network than your phone or Home Assistant. Look at the router or controller that actually manages that network.
4. **Look for more than one address or interface.** A device might expose different Wi-Fi and Bluetooth identifiers. Only the Wi-Fi/network MAC is useful for matching a router's Wi-Fi clients.
5. **If another device has the name you expected**, verify its full MAC address. Many similar TP-Link devices can appear under the same generic name.
6. **If you cannot find any reliable match**, try Tapo Local's built-in discovery instead of guessing an address.

Avoid unplugging, factory-resetting, or deleting a working smart lock just to identify its IP. You can usually investigate from the router without touching the lock.

### Devices on another VLAN or subnet

A **VLAN** is simply a separate network, often used to keep smart-home devices apart from computers and phones.

For example, Home Assistant might be on `192.168.1.x` while smart devices are on `172.20.x.x`. In that case:

- Look in the router or network controller that manages the smart-device network.
- You can use Tapo Local's **Network to scan** field with its **CIDR** (network address), such as `172.20.0.0/16`. That automatically describes the subnet mask. You do **not** need a second subnet-mask field.
- If you find an individual device address, such as `172.20.0.42`, enter it in **Device IP address or hostname** instead.
- Home Assistant must be allowed by your existing network rules to communicate with that device. A device can appear in the router list but still be unreachable from Home Assistant.

The `/16` network contains more than 65,000 possible usable addresses, so a scan may take several minutes. **Do not scan a huge network when you already know the device IP.**

## Put the IP address into Tapo Local

### Adding a device for the first time

1. In Home Assistant, go to **Settings → Devices & services → Add integration**.
2. Choose **Tapo Local**.
3. Enter the IP address you found (for example `192.168.1.47`) in **Device IP address or hostname**.
4. Leave **Network to scan** blank. This field is only for discovery when you do not know the device IP.
5. Select **Submit** and follow the prompts.

### If the device was added before

Open **Settings → Devices & services → Tapo Local**, find that device's existing entry, open its menu, and select **Reconfigure** to enter the new address. **Do not delete and re-add it.** This is especially important for DL100 locks because an existing encrypted session may still be valid.

### Optional: Keep the IP from changing

If your router offers **DHCP Reservation**, **Address Reservation**, or **Reserve IP**, you can make it give the same IP address to the same device's MAC address after reconnecting.

This is optional—not required for Tapo Local. Follow your router's instructions, reserve an address appropriate for that network, and avoid conflicting with another device. You do **not** need to change the device's network settings or enter a manual static IP on the device itself.

## Still stuck?

Use the [Tapo Local support guide](../SUPPORT.md) or [open a bug report](https://github.com/gigabytegrove/tapo-local/issues/new/choose).

Include the device model, Home Assistant and Tapo Local versions, whether the device is on another VLAN, and the **visible error message**. Please **do not post your entire router's client list**, HomeKit pairing codes, full MAC addresses, login information, or unredacted diagnostics.
