"""Expiry-aware, serialized transport for the pinned pypentair 0.4.3 API.

Cognito user JWTs and identity-pool AWS session credentials have independent
lifetimes. Never use JWT freshness as a proxy for signing credential freshness.
Account login/discovery models remain provided by pypentair; only its transport
and signer lifecycle are adapted here. No credentials enter diagnostics/logs.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from typing import Any
from urllib.parse import urljoin

import requests
from boto3 import client as boto_client
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.credentials import Credentials
from botocore.exceptions import ClientError
from pypentair import Pentair as BasePentair
from pypentair import PentairAuthenticationError
from pypentair.const import IDENTITY_POOL_ID, REGION_NAME, USER_POOL_ID
from pypentair.utils import decode

_BASE_URL = "https://api.pentair.cloud/"
_REFRESH_MARGIN = 300


def _token_ttl(token: str | None) -> float:
    try:
        part = token.split(".")[1]
        return (
            float(
                json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))[
                    "exp"
                ]
            )
            - time.time()
        )
    except (AttributeError, IndexError, ValueError, KeyError, TypeError):
        return 0


def _expired_response(response: requests.Response) -> bool:
    if response.status_code not in (401, 403):
        return False
    try:
        payload = response.json()
        message = str(payload.get("message", "")).lower()
    except (ValueError, AttributeError):
        return False
    return "token" in message and "expired" in message


class Pentair(BasePentair):
    """One lock covers refresh, signing, and HTTP for every account request."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._lock = threading.RLock()
        self._auth = None
        self._credentials_expire_at = 0.0
        self._signer_token = None
        self.user_refreshes = 0
        self.signer_refreshes = 0
        self.expiry_retries = 0
        self.last_success = None

    def get_auth(self) -> SigV4Auth:
        with self._lock:
            try:
                user = self.get_user()
                if _token_ttl(self.id_token) < _REFRESH_MARGIN:
                    user.renew_access_token()
                    self.user_refreshes += 1
                if (
                    self._auth is None
                    or self._signer_token != self.id_token
                    or time.time() >= self._credentials_expire_at - _REFRESH_MARGIN
                ):
                    identity = boto_client(
                        "cognito-identity",
                        region_name=REGION_NAME,
                        config=Config(
                            connect_timeout=10,
                            read_timeout=10,
                            retries={"max_attempts": 1},
                        ),
                    )
                    logins = {
                        f"cognito-idp.{REGION_NAME}.amazonaws.com/{decode(USER_POOL_ID)}": self.id_token
                    }
                    response = identity.get_id(
                        IdentityPoolId=decode(IDENTITY_POOL_ID), Logins=logins
                    )
                    values = identity.get_credentials_for_identity(
                        IdentityId=response["IdentityId"],
                        Logins=logins,
                    )["Credentials"]
                    expiry = values["Expiration"].timestamp()
                    if expiry <= time.time():
                        raise RuntimeError(
                            "AWS returned already-expired signing credentials"
                        )
                    self._auth = SigV4Auth(
                        Credentials(
                            values["AccessKeyId"],
                            values["SecretKey"],
                            values["SessionToken"],
                        ),
                        "execute-api",
                        REGION_NAME,
                    )
                    self._credentials_expire_at = expiry
                    self._signer_token = self.id_token
                    self.signer_refreshes += 1
                return self._auth
            except ClientError as err:
                if err.response.get("Error", {}).get("Code") in {
                    "NotAuthorizedException",
                    "UserNotFoundException",
                }:
                    raise PentairAuthenticationError(
                        "Pentair login requires reauthentication"
                    ) from err
                raise

    def _request(
        self, method: str, path: str, fields: dict[str, str] | None = None
    ) -> dict:
        with self._lock:
            for attempt in range(2):
                # Refresh BEFORE capturing the JWT header, not after.
                auth = self.get_auth()
                body = json.dumps({"payload": fields}) if fields is not None else None
                headers = {"x-amz-id-token": self.id_token}
                if body is not None:
                    headers.update(
                        {
                            "content-type": "application/json; charset=UTF-8",
                            "user-agent": "aws-amplify/4.3.10 react-native",
                        }
                    )
                req = AWSRequest(
                    method=method,
                    url=urljoin(_BASE_URL, path),
                    data=body,
                    headers=headers,
                )
                auth.add_auth(req)
                prepared = req.prepare()
                response = requests.request(
                    method,
                    prepared.url,
                    data=body,
                    headers=dict(prepared.headers),
                    timeout=(10, 15),
                )
                if attempt == 0 and _expired_response(response):
                    self._auth = None
                    self._credentials_expire_at = 0
                    self.expiry_retries += 1
                    continue
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or not isinstance(
                    result.get("data"), (dict, list)
                ):
                    raise ValueError("Pentair returned an invalid response envelope")
                self.last_success = time.time()
                return result
        raise RuntimeError("Unreachable request retry state")

    def get_devices(self) -> dict:
        return self._request("GET", "device/device-service/user/devices")

    def get_device(self, device_id: str) -> dict:
        return self._request("GET", f"device/device-service/user/device/{device_id}")

    def set_fields(self, device_id: str, fields: dict[str, str]) -> dict:
        result = self._request(
            "PUT", f"device/device-service/user/device/{device_id}", fields
        )
        if result["data"].get("code") != "set_device_success":
            raise RuntimeError("Pentair did not acknowledge the device command")
        return result
