"""Pentair coordinator."""

from __future__ import annotations

import base64
from datetime import timedelta
import json
import logging
import time
from typing import Any
from urllib.parse import urljoin

from botocore.awsrequest import AWSRequest
from deepdiff import DeepDiff
from pypentair import Pentair
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

# Pentair Home write endpoint.  pypentair 0.4.1 exposes only read methods
# (`get_device`, `get_devices`), so we issue PUTs directly using the same
# SigV4-signed AWS Cognito auth the library already produces.  Body shape
# is `{"payload": {"<field>": "<value>"}}`; all values are strings.  Mirrors
# the pattern in thk-socal/hacs-pentair-switch's IntelliFlo 3 work.
_PENTAIR_BASE_URL = "https://api.pentair.cloud/"
_PENTAIR_DEVICE_PATH = "device/device-service/user/device/{device_id}"
_PENTAIR_USER_AGENT = "aws-amplify/4.3.10 react-native"

# Pentair Cognito id_tokens are 60-min JWTs (ttl = exp - iat = 3600s).
# We refresh proactively when fewer than this many seconds remain on the
# cached id_token so we never *intentionally* issue a stale token.  The
# 401/403-reactive refresh below is the safety net for mid-call expiry
# or server-side revoke.
_REFRESH_HORIZON_SEC = 5 * 60

_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = 30


def _id_token_ttl(client: Pentair) -> int:
    """Seconds remaining on the cached id_token; 0 if absent / unparseable."""
    tok = getattr(client, "id_token", None)
    if not tok:
        return 0
    try:
        payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
        return max(0, int(payload.get("exp", 0)) - int(time.time()))
    except Exception:  # pylint: disable=broad-except
        return 0


def _force_token_refresh(client: Pentair) -> None:
    """Renew Cognito tokens using the cached refresh_token.

    pycognito's ``check_token()`` does not reliably detect a stale id_token
    in long-running processes (symptom: repeated ``403 — The security
    token included in the request is expired`` after ~1 hour of uptime).
    Calling ``renew_access_token()`` directly bypasses the broken exp
    check and unconditionally swaps in fresh tokens via the refresh_token.
    """
    try:
        client.get_user().renew_access_token()
        _LOGGER.debug(
            "Pentair tokens renewed (new id_token ttl=%ds)", _id_token_ttl(client)
        )
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Pentair renew_access_token failed: %s", err)
        raise


def _ensure_token_fresh(client: Pentair) -> None:
    """Proactively refresh the id_token when within the refresh horizon."""
    ttl = _id_token_ttl(client)
    if ttl < _REFRESH_HORIZON_SEC:
        _LOGGER.debug(
            "Pentair id_token ttl=%ds < %ds — proactively renewing",
            ttl,
            _REFRESH_HORIZON_SEC,
        )
        _force_token_refresh(client)


def _is_auth_error(err: BaseException) -> bool:
    """Return True if *err* is a Pentair API auth failure (401 / 403)."""
    return (
        isinstance(err, requests.HTTPError)
        and err.response is not None
        and err.response.status_code in (401, 403)
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
            if devices := await self.hass.async_add_executor_job(
                _get_devices_with_refresh, self.api
            ):
                diff = DeepDiff(
                    self.devices,
                    devices,
                    ignore_order=True,
                    report_repetition=True,
                    verbose_level=2,
                )
                _LOGGER.debug("Devices updated: %s", diff if diff else "no changes")
                self.devices = devices
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unknown exception while updating Pentair data: %s", err)
            raise UpdateFailed(err) from err
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
            _signed_put_sync, self.api, self.device_id, fields
        )

    async def _async_update_data(self):
        """Update data via library, refresh token if necessary."""
        try:
            if device := await self.hass.async_add_executor_job(
                _get_device_with_refresh, self.api, self.device_id
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
                    diff if diff else "no changes",
                )
                return device
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unknown exception while updating Pentair data: %s", err)
            raise UpdateFailed(err) from err
        else:
            return None


def _get_devices_with_refresh(client: Pentair) -> dict[str, Any] | None:
    """Blocking ``client.get_devices()`` with proactive + reactive refresh."""
    _ensure_token_fresh(client)
    try:
        return client.get_devices()
    except requests.HTTPError as err:
        if not _is_auth_error(err):
            raise
        _LOGGER.info(
            "Pentair get_devices got HTTP %d despite pre-flight check — refreshing and retrying",
            err.response.status_code,
        )
        _force_token_refresh(client)
        return client.get_devices()


def _get_device_with_refresh(client: Pentair, device_id: str) -> dict[str, Any] | None:
    """Blocking ``client.get_device(id)`` with proactive + reactive refresh."""
    _ensure_token_fresh(client)
    try:
        return client.get_device(device_id)
    except requests.HTTPError as err:
        if not _is_auth_error(err):
            raise
        _LOGGER.info(
            "Pentair get_device(%s) got HTTP %d despite pre-flight check — refreshing and retrying",
            device_id,
            err.response.status_code,
        )
        _force_token_refresh(client)
        return client.get_device(device_id)


def _do_signed_put(
    client: Pentair, device_id: str, fields: dict[str, str]
) -> requests.Response:
    """Build, sign, and execute one SigV4 PUT.  Returns the raw response so
    callers can decide how to react to non-2xx codes (e.g. retry on auth
    errors)."""
    url = urljoin(_PENTAIR_BASE_URL, _PENTAIR_DEVICE_PATH.format(device_id=device_id))
    body = json.dumps({"payload": fields})
    req = AWSRequest(
        method="PUT",
        url=url,
        data=body,
        headers={
            "x-amz-id-token": client.id_token,
            "content-type": "application/json; charset=UTF-8",
            "user-agent": _PENTAIR_USER_AGENT,
        },
    )
    client.get_auth().add_auth(req)
    prepared = req.prepare()
    return requests.request(
        method="PUT",
        url=prepared.url,
        data=body,
        headers=dict(prepared.headers),
        timeout=15,
    )


def _signed_put_sync(
    client: Pentair, device_id: str, fields: dict[str, str]
) -> dict[str, Any]:
    """Blocking SigV4-signed PUT helper, called from `async_add_executor_job`.

    Build an AWSRequest, let pypentair's existing `get_auth()` add the SigV4
    signature, then `requests.request` with the signed headers.  Pre-flight
    refreshes the id_token when within `_REFRESH_HORIZON_SEC` of expiry; on
    a 401/403 from the API it refreshes once more and retries the call
    exactly once.  Validates that Pentair acknowledged with
    `set_device_success`.
    """
    _ensure_token_fresh(client)
    response = _do_signed_put(client, device_id, fields)
    if response.status_code in (401, 403):
        _LOGGER.info(
            "Pentair PUT got HTTP %d despite pre-flight check — refreshing and retrying",
            response.status_code,
        )
        _force_token_refresh(client)
        response = _do_signed_put(client, device_id, fields)
    response.raise_for_status()
    payload = response.json()
    if payload.get("data", {}).get("code") != "set_device_success":
        raise RuntimeError(f"Pentair API rejected write: {payload}")
    return payload
