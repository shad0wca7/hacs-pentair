<!-- BEGIN AUTO-GENERATED HEADER -->

[![Release](https://img.shields.io/github/v/release/natekspencer/hacs-pentair?style=for-the-badge)](https://github.com/natekspencer/hacs-pentair/releases)
[![HACS Badge](https://img.shields.io/badge/HACS-custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor_💜-6f42c1?style=for-the-badge&logo=github&logoColor=white&labelColor=grey)](https://github.com/sponsors/natekspencer)

![Downloads](https://img.shields.io/github/downloads/natekspencer/hacs-pentair/total?style=flat-square)
![Latest Downloads](https://img.shields.io/github/downloads/natekspencer/hacs-pentair/latest/total?style=flat-square)

<!-- END AUTO-GENERATED HEADER -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://brands.home-assistant.io/pentair_cloud/dark_logo.png">
  <img alt="Pentair logo" src="https://brands.home-assistant.io/pentair_cloud/logo.png">
</picture>

# Pentair Home for Home Assistant

Home Assistant integration for Pentair Home devices.

## 🌊 Supported devices

The integration auto-discovers every device on your Pentair Home account and exposes the underlying telemetry as `sensor` / `binary_sensor` entities for diagnostics.  On top of that, the device types below get first-class **control** entities:

### Color Sync (`deviceType: PLC1`, e.g. part **618031** — MicroBrite RGB pool lights)

| Entity | Type | What it does | Backing field |
|---|---|---|---|
| Pool lights | `switch` | On / off | `d13` (0/1) |
| Pool lights mode | `select` | One of 12 scenes: Red, White, Magenta, Green, Blue, SAm, Party, Romance, Caribbean, American, Sunset, Royal | `d1` (0..4, 7..13) |
| Pool lights hold | `button` | Freezes the current animation on its present color | `d1` = 5 |
| Pool lights recall | `button` | Resumes the last show that was running before Hold | `d1` = 6 |

> The Color Sync controller is a cloud-only product (no LAN API).  Control happens via Pentair's REST endpoint, signed with the AWS Cognito tokens this integration already maintains.

### IntelliFlo / IntelliCenter and other Pentair devices

Read-only telemetry today — `switch` / `select` / `button` platforms are scoped to PLC1, but the platform files use device-type lookup tables so adding more device families is just a matter of describing the right fields.

## 🍴 Fork notice — installing this build

This repository is a fork of [natekspencer/hacs-pentair](https://github.com/natekspencer/hacs-pentair) that adds **Color Sync (PLC1) control entities** (the switch / select / button platforms above).  The change is open upstream as [PR #26](https://github.com/natekspencer/hacs-pentair/pull/26); pending merge, install this fork directly:

1. In Home Assistant, open **HACS**
2. Click the vertical ellipsis (⋮) → **Custom repositories**
3. Enter `CZX6/hacs-pentair` in the _Repository_ field and select `Integration` in the _Type_ dropdown
4. Click **ADD**
5. Search for `Pentair Home` and **DOWNLOAD**
6. Restart Home Assistant

Already running upstream `natekspencer/hacs-pentair`?  Remove that integration first (Settings → Devices & services → Pentair Home → ⋮ → Delete) to avoid a duplicate domain registration, then install this fork via the steps above and re-add the integration.

> **What's bundled beyond upstream:** the new Color Sync platforms, plus a proactive + reactive Cognito token-refresh layer in `coordinator.py` that fixes the `403 — The security token included in the request is expired` failure mode the upstream integration hits after ~1 hour of uptime.  See PR #26 for the full rationale.

<!-- BEGIN AUTO-GENERATED INSTALLATION -->

## ⬇️ Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=natekspencer&repository=hacs-pentair&category=integration)

1. Use the **My Home Assistant** badge above, or from within Home Assistant, click on **HACS**
2. Click the vertical ellipsis (⋮) → **Custom repositories**
3. Enter `natekspencer/hacs-pentair` in the _Repository_ field and select `Integration` in the _Type_ dropdown
4. Click **ADD**
5. Close the _Custom repositories_ window
6. Search for `Pentair Home` and click on the appropriate repository
7. Click **DOWNLOAD**
8. Restart Home Assistant

### Manual

If you prefer manual installation:

1. Download or clone this repository
2. Copy the `custom_components/pentair_cloud` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

> ⚠️ Manual installation will not provide automatic update notifications. HACS installation is recommended unless you have a specific need.

## ➕ Setup

Once installed, you can set up the integration by clicking on the following badge:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pentair_cloud)

Alternatively:

1. Go to [Settings > Devices & services](https://my.home-assistant.io/redirect/integrations/)
2. In the bottom-right corner, select **Add integration**
3. Type `Pentair Home` and select the **Pentair Home** integration
4. Follow the instructions to add the integration to your Home Assistant
<!-- END AUTO-GENERATED INSTALLATION -->

---

<!-- BEGIN AUTO-GENERATED FOOTER -->

## ❤️ Support Me

I maintain this Home Assistant integration in my spare time. If you find it useful, consider supporting development:

- 💜 [Sponsor me on GitHub](https://github.com/sponsors/natekspencer)
- ☕ [Buy me a coffee / beer](https://ko-fi.com/natekspencer)
- 💸 [PayPal (direct support)](https://www.paypal.com/paypalme/natekspencer)
- ⭐ [Star this project](https://github.com/natekspencer/hacs-pentair)
- 📦 If you’d like to support in other ways, such as donating hardware for testing, feel free to [reach out to me](https://github.com/natekspencer)

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=natekspencer/hacs-pentair)](https://www.star-history.com/#natekspencer/hacs-pentair)

<!-- END AUTO-GENERATED FOOTER -->
