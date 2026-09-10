"""Exercise the real client/signing code with fake AWS and HTTP boundaries."""

import base64
import importlib.util
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests

path = Path(__file__).parents[1] / "custom_components/pentair_cloud/client.py"
if path.exists():
    spec = importlib.util.spec_from_file_location("pentair_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
else:
    # RED: the pinned upstream implementation used before the fix.
    import pypentair.pentair as module


def token(exp):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode()
    return "test." + payload + ".not-a-real-token"


class User:
    def __init__(self):
        self.id_token = token(time.time() + 3600)
        self.access_token = "fixture"
        self.refresh_token = "fixture"
        self.renewals = 0

    def check_token(self):
        return False

    def renew_access_token(self):
        self.renewals += 1
        self.id_token = token(time.time() + 3600 + self.renewals)


@pytest.fixture
def client(monkeypatch):
    class Identity:
        calls = 0

        def get_id(self, **kwargs):
            return {"IdentityId": "fixture"}

        def get_credentials_for_identity(self, **kwargs):
            self.calls += 1
            return {
                "Credentials": {
                    "AccessKeyId": "fixture-key-" + str(self.calls),
                    "SecretKey": "fixture-not-a-secret",
                    "SessionToken": "fixture-session",
                    "Expiration": datetime.now(UTC) + timedelta(seconds=600),
                }
            }

    identity = Identity()
    monkeypatch.setattr(module, "boto_client", lambda *a, **k: identity)
    c = module.Pentair(username="fixture")
    c._user = User()
    c.identity = identity
    return c


def response(status=200, message=None):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(
        message or {"data": {"code": "set_device_success"}}
    ).encode()
    return r


def test_aws_expiry_refreshes_even_when_jwt_is_fresh(client):
    first = client.get_auth()
    client._credentials_expire_at = time.time() - 1
    assert client.get_auth() is not first
    assert client.identity.calls == 2


def test_renewed_user_token_replaces_signer(client):
    first = client.get_auth()
    client._user.renew_access_token()
    assert client.get_auth() is not first


def test_unexpired_signer_is_reused(client):
    assert client.get_auth() is client.get_auth()
    assert client.identity.calls == 1


def test_expired_aws_response_retries_with_new_signer(client, monkeypatch):
    keys = []

    def send(*args, **kwargs):
        keys.append(kwargs["headers"]["Authorization"])
        return (
            response(
                403,
                {"message": "The security token included in the request is expired"},
            )
            if len(keys) == 1
            else response()
        )

    monkeypatch.setattr(module.requests, "request", send)
    assert client.get_device("fixture")["data"]
    assert len(keys) == 2
    assert keys[0] != keys[1]


def test_persistent_expiry_is_bounded(client, monkeypatch):
    calls = []

    def send(*args, **kwargs):
        calls.append(1)
        return response(
            403, {"message": "The security token included in the request is expired"}
        )

    monkeypatch.setattr(module.requests, "request", send)
    with pytest.raises(requests.HTTPError):
        client.get_device("fixture")
    assert len(calls) == 2


def test_permission_denial_not_retried(client, monkeypatch):
    calls = []

    def send(*args, **kwargs):
        calls.append(1)
        return response(403, {"message": "Access denied"})

    monkeypatch.setattr(module.requests, "request", send)
    with pytest.raises(requests.HTTPError):
        client.get_device("fixture")
    assert len(calls) == 1


def test_concurrent_requests_are_serialized(client, monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    def send(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
        time.sleep(0.01)
        with lock:
            active -= 1
        return response()

    monkeypatch.setattr(module.requests, "request", send)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(client.get_device, ["fixture"] * 8))
    assert peak == 1


def test_write_uses_new_token_header_and_validates_ack(client, monkeypatch):
    client._user.id_token = token(time.time() - 10)
    sent = []

    def send(*args, **kwargs):
        sent.append(kwargs)
        return response()

    monkeypatch.setattr(module.requests, "request", send)
    client.set_fields("fixture", {"d13": "1"})
    assert sent[0]["headers"]["x-amz-id-token"] == client.id_token
    assert json.loads(sent[0]["data"]) == {"payload": {"d13": "1"}}
    assert client._user.renewals == 1
    monkeypatch.setattr(
        module.requests,
        "request",
        lambda *a, **k: response(200, {"data": {"code": "rejected"}}),
    )
    with pytest.raises(RuntimeError, match="acknowledge"):
        client.set_fields("fixture", {"d13": "1"})


def test_revoked_refresh_token_is_auth_failure(client):
    from botocore.exceptions import ClientError
    from pypentair import PentairAuthenticationError

    client._user.id_token = token(0)

    def revoked():
        raise ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "fixture"}},
            "Refresh",
        )

    client._user.renew_access_token = revoked
    with pytest.raises(PentairAuthenticationError):
        client.get_device("fixture")


def test_timeout_does_not_replay_command(client, monkeypatch):
    calls = []

    def send(*a, **k):
        calls.append(1)
        raise requests.Timeout("fixture timeout")

    monkeypatch.setattr(module.requests, "request", send)
    with pytest.raises(requests.Timeout):
        client.set_fields("fixture", {"d1": "5"})
    assert len(calls) == 1


def test_invalid_envelope_is_failure(client, monkeypatch):
    monkeypatch.setattr(
        module.requests, "request", lambda *a, **k: response(200, {"unexpected": True})
    )
    with pytest.raises(ValueError):
        client.get_device("fixture")


def test_multiple_expiry_cycles_without_client_rebuild(client, monkeypatch):
    monkeypatch.setattr(module.requests, "request", lambda *a, **k: response())
    for _ in range(4):
        client._credentials_expire_at = 0
        client.get_device("fixture")
    assert client.signer_refreshes == 4
    assert client.expiry_retries == 0


def test_read_and_write_share_lock(client, monkeypatch):
    active = 0
    peak = 0

    def send(*a, **k):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(0.01)
        active -= 1
        return response()

    monkeypatch.setattr(module.requests, "request", send)
    with ThreadPoolExecutor(max_workers=2) as pool:
        read = pool.submit(client.get_device, "fixture")
        write = pool.submit(client.set_fields, "fixture", {"d1": "5"})
        read.result()
        write.result()
    assert peak == 1
