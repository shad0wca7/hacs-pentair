"""Allowlisted health diagnostics: never include account or device payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import PentairConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PentairConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    api = coordinator.api
    return {
        "client": {
            "user_refreshes": api.user_refreshes,
            "signer_refreshes": api.signer_refreshes,
            "expiry_retries": api.expiry_retries,
            "last_success": api.last_success,
        },
        "devices": [
            {
                "last_update_success": dc.last_update_success,
                "consecutive_failures": dc._consecutive_failures,
            }
            for dc in coordinator.device_coordinators
        ],
    }
