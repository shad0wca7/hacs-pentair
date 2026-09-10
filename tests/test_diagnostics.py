"""Downloaded diagnostics must be allowlisted, not raw cloud payloads."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_diagnostics_exclude_account_and_device_payloads():
    path = Path(__file__).parents[1] / "custom_components/pentair_cloud/diagnostics.py"
    spec = importlib.util.spec_from_file_location("diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    api = SimpleNamespace(
        user_refreshes=1,
        signer_refreshes=2,
        expiry_retries=0,
        last_success=123,
        id_token="must-not-appear",
    )
    dc = SimpleNamespace(
        last_update_success=True,
        _consecutive_failures=0,
        data={"private": "must-not-appear"},
    )
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(api=api, device_coordinators=[dc])
    )
    result = asyncio.run(module.async_get_config_entry_diagnostics(None, entry))
    assert result["client"]["signer_refreshes"] == 2
    assert "must-not-appear" not in str(result)
    assert set(result) == {"client", "devices"}
