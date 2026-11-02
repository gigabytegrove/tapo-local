# Help with Tapo Local

If something is not working, try these steps before opening an issue.

1. Check your version in **Settings → Devices & services → Tapo Local**. Compare with the [latest public release](https://github.com/gigabytegrove/tapo-local/releases/latest).
2. Restart Home Assistant after installing or updating.
3. Verify the device's current IP address in your router or the Tapo/Kasa app. Use **Reconfigure** on its existing entry if the IP changed.
4. If discovery fails, add the device using its IP address. For a separate network, you can scan its CIDR address, such as 172.20.0.0/16, without entering a separate subnet mask.
5. For DL100 locks, use the **original Tapo owner account**. If more than one lock is listed, choose the correct one; do not delete a working lock entry.
6. Check **Settings → System → Logs** for a Tapo Local error. Note the message and numeric error code, if any.

## Report a bug

Open a [GitHub issue](https://github.com/gigabytegrove/tapo-local/issues/new/choose). Please include the Tapo Local and Home Assistant versions, exact model and firmware (when known), what you tried, what happened, and the visible error code.

**Do not share passwords, cloud tokens, HomeKit setup codes, DL100 session files, device IDs, or unredacted diagnostics.** If you are unsure whether your log contains secrets, share the visible error text only. Security issues must be reported privately using [SECURITY.md](SECURITY.md), not public issues.

For features or supported-device requests, use the same [issue chooser](https://github.com/gigabytegrove/tapo-local/issues/new/choose). Community discussion should follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
