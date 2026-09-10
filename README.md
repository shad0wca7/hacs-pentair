# Pentair Home for Home Assistant

[![Release](https://img.shields.io/github/v/release/shad0wca7/hacs-pentair)](https://github.com/shad0wca7/hacs-pentair/releases)
[![Validation](https://github.com/shad0wca7/hacs-pentair/actions/workflows/validate.yaml/badge.svg)](https://github.com/shad0wca7/hacs-pentair/actions/workflows/validate.yaml)
[![HACS custom](https://img.shields.io/badge/HACS-custom-41BDF5)](https://hacs.xyz/)

A maintained fork of [natekspencer/hacs-pentair](https://github.com/natekspencer/hacs-pentair), with Color Sync (PLC1) controls derived from [CZX6's work](https://github.com/CZX6/hacs-pentair). This integration uses the **Pentair Home cloud API**; internet access and a Pentair Home account are required. It does not implement local/LAN control.

## Install this fork

Requires Home Assistant **2026.1.0 or newer** and HACS.

1. HACS → menu → **Custom repositories**.
2. Add **`https://github.com/shad0wca7/hacs-pentair`**, category **Integration**.
3. Download **Pentair Home** from this repository and restart Home Assistant.
4. Settings → Devices & services → Add integration → **Pentair Home**, then sign in.

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=shad0wca7&repository=hacs-pentair&category=integration)

### Updating or switching from another fork

Back up your configuration first. All these forks use the same `pentair_cloud` domain: only one implementation can be installed. Replace the existing HACS repository selection/component files with this fork, then restart Home Assistant. **Keep the existing Pentair config entry and entity IDs.** Do not delete/re-add the integration merely to update its code: deletion logs the account out and can disrupt existing entities and automations. HACS menu wording varies by version; if it requires removing the old download, preserve the HA config entry.

For manual installation, copy `custom_components/pentair_cloud` into the Home Assistant `custom_components` directory and restart. Manual installs do not receive HACS update notifications.

## Supported controls

First-class controls are scoped to **Color Sync (`PLC1`)**, including the 618031 controller used with compatible Pentair color lights. The integration creates a switch; a light entity may also exist if your HA configuration wraps that switch.

| Entity | Function | Cloud field |
|---|---|---|
| Switch | Power on/off | `d13`: 0/1 |
| Select | Red, White, Magenta, Green, Blue, SAm, Party, Romance, Caribbean, American, Sunset, Royal | `d1`: 0–4, 7–13 |
| Hold button | Sends the controller's Hold command | `d1`: 5 |
| Recall button | Sends the controller's Recall command | `d1`: 6 |

Hold/Recall labels describe controller commands, not a guarantee that Recall resumes an animation. Consult the controller/light manual for physical behavior. Buttons can show `unknown` until first pressed; that is not the same as `unavailable`.

Other device types may expose inherited sensor/binary-sensor telemetry, but this fork does not promise control support or verified compatibility for every Pentair product. Diagnostic values depend on device-specific cloud field encodings.

## Reliability and authentication

**v1.0.0 has a known hourly authentication defect:** it refreshes Cognito login tokens without reliably replacing expired AWS signing credentials. Its three-failure watchdog can recover by reloading, but does not eliminate outages.

**v1.0.1** introduces an expiry-aware client adapter for pinned `pypentair==0.4.3`:

- Tracks the AWS credential expiration returned by Cognito Identity independently of login-token expiry; refreshes five minutes early.
- Rebuilds signing credentials when the user token changes and captures request headers only after refresh.
- Serializes account reads, writes and refreshes to avoid competing signer/token updates.
- Retries an explicit expired-token response once with rebuilt signing credentials. Ordinary authorization denials and command timeouts are not blindly replayed.
- Sends revoked-login failures to HA reauthentication.
- Retains the three-consecutive-failure reload fallback with a one-hour cooldown.

Regression tests cover independent credential expiry, token replacement, retry bounds, concurrent requests, revoked login, command acknowledgement and timeouts. Passing tests is not a guarantee of uninterrupted cloud service; deployment must be observed across real expiry cycles. Device connectivity, internet availability and Pentair outages remain separate failure modes.

### Troubleshooting

Check Settings → System → Logs for `pentair_cloud`. An occasional recovery reload is a fallback event; hourly reloads are a fault, not healthy operation. Download integration diagnostics for credential-refresh/retry counters and coordinator health (no credentials or device payloads are included). Reauthenticate when HA requests it; do not repeatedly delete the integration.

Known separate issue: some PLC1 device-time values do not match the upstream decoder, causing conversion errors or implausible dates. Those telemetry values should not be treated as authoritative. This release does not guess a new time encoding or change lighting schedules.

Report problems at [this fork's issue tracker](https://github.com/shad0wca7/hacs-pentair/issues), including integration/HA versions and redacted errors. Never post tokens, account credentials, full device payloads or unredacted diagnostics from other integrations.

## Development and provenance

Run `python -m pytest -q` after installing `requirements-test.txt`. The tests isolate AWS/HTTP boundaries; they do not contact your account or operate lights.

- Original integration and pypentair: [Nate Spencer](https://github.com/natekspencer).
- Color Sync controls and earlier token-refresh work: [CZX6](https://github.com/CZX6/hacs-pentair).
- [Upstream PR #26](https://github.com/natekspencer/hacs-pentair/pull/26) is **closed and unmerged**, not a pending installation path.
- Wrapped-field compatibility derives from [upstream PR #31](https://github.com/natekspencer/hacs-pentair/pull/31).
- Fork maintenance and credential-lifecycle repair: [shad0wca7](https://github.com/shad0wca7/hacs-pentair).

Original licensing and attribution are retained in [LICENSE](LICENSE). If you wish to support the original author, [Nate's GitHub Sponsors](https://github.com/sponsors/natekspencer) is an **upstream-author** support link, not a donation to this fork's maintainer.
