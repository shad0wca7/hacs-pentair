"""Pentair coordinator."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from deepdiff import DeepDiff
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pypentair import PentairAuthenticationError

from .client import Pentair
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = 30

# Last-resort recovery for repeated transport failures, not a guarantee of
# cloud availability. Preserve cooldown across config-entry reloads.
_AUTO_RELOAD_MIN_FAILURES = 3
_AUTO_RELOAD_COOLDOWN_SEC = 3600
_auto_reload_last: dict[str, float] = {}


def _note_update_failure(coordinator) -> None:
    """Count consecutive failures; trigger a config-entry reload when wedged."""
    entry_id = coordinator.config_entry.entry_id
    coordinator._consecutive_failures = (
        getattr(coordinator, "_consecutive_failures", 0) + 1
    )
    failures = coordinator._consecutive_failures
    if failures < _AUTO_RELOAD_MIN_FAILURES:
        return
    now = time.monotonic()
    if now - _auto_reload_last.get(entry_id, float("-inf")) < _AUTO_RELOAD_COOLDOWN_SEC:
        return
    _auto_reload_last[entry_id] = now
    _LOGGER.warning(
        "Pentair update failed %s consecutive times — auto-reloading config entry "
        "%s to rebuild the client (next auto-reload in %ss)",
        failures,
        entry_id,
        _AUTO_RELOAD_COOLDOWN_SEC,
    )
    coordinator.hass.async_create_task(
        coordinator.hass.config_entries.async_reload(entry_id)
    )


class PentairDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: Pentair
    ) -> None:
        """Initialize."""
        self.api = client
        self.devices: dict[str, list[dict[str, Any]]] = {}
        self.device_coordinators: list[PentairDeviceDataUpdateCoordinator] = []
        self._consecutive_failures = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def get_device(self, device_id: str) -> dict | None:
        """Get device by id."""
        return next(
            (
                device
                for device in self.devices.get("data", [])
                if device["deviceId"] == device_id
            ),
            None,
        )

    def get_devices(self, device_type: str | None = None) -> list[dict]:
        """Get device by id."""
        return [
            device
            for device in self.devices.get("data", [])
            if device_type is None or device["deviceType"] == device_type
        ]

    async def _async_update_data(self):
        """Update data via library, refresh token if necessary."""
        try:
            if devices := await self.hass.async_add_executor_job(self.api.get_devices):
                diff = DeepDiff(
                    self.devices,
                    devices,
                    ignore_order=True,
                    report_repetition=True,
                    verbose_level=2,
                )
                _LOGGER.debug("Devices updated: %s", bool(diff))
                self.devices = devices
                self._consecutive_failures = 0
        except PentairAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Pentair login requires reauthentication"
            ) from err
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Pentair update failed (%s)", type(err).__name__)
            _note_update_failure(self)
            raise UpdateFailed(f"Pentair update failed ({type(err).__name__})") from err
        return self.devices


class PentairDeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the device endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Pentair,
        device_id: str,
    ) -> None:
        """Initialize."""
        self.api = client
        self.device_id = device_id
        self._consecutive_failures = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    def get_device_data(self) -> dict | None:
        """Get the device data."""
        if self.data and (data := self.data.get("data")):
            return data
        return None

    async def async_set_fields(self, fields: dict[str, str]) -> dict[str, Any]:
        """Send a SigV4-signed PUT updating one or more device fields.

        All field values must be strings (Pentair Home's contract — even
        numeric fields).  Returns the parsed response body.  Raises
        `RuntimeError` if Pentair doesn't reply with
        `code == "set_device_success"`.
        """
        return await self.hass.async_add_executor_job(
            self.api.set_fields, self.device_id, fields
        )

    async def _async_update_data(self):
        """Update data via library, refresh token if necessary."""
        try:
            if device := await self.hass.async_add_executor_job(
                self.api.get_device, self.device_id
            ):
                diff = DeepDiff(
                    self.data,
                    device,
                    ignore_order=True,
                    report_repetition=True,
                    verbose_level=2,
                )
                _LOGGER.debug(
                    "Device %s updated: %s",
                    self.device_id,
                    bool(diff),
                )
                self._consecutive_failures = 0
                return device
        except PentairAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Pentair login requires reauthentication"
            ) from err
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Pentair update failed (%s)", type(err).__name__)
            _note_update_failure(self)
            raise UpdateFailed(f"Pentair update failed ({type(err).__name__})") from err
        else:
            return None
