"""Unit-test the scheduling function without requiring an HA installation."""

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace


def test_reload_threshold_cooldown_and_first_hour():
    tree = ast.parse(
        (
            Path(__file__).parents[1] / "custom_components/pentair_cloud/coordinator.py"
        ).read_text()
    )
    fn = next(
        x
        for x in tree.body
        if isinstance(x, ast.FunctionDef) and x.name == "_note_update_failure"
    )
    now = [10.0]
    calls = []

    async def reload(entry):
        calls.append(entry)

    ns = {
        "time": SimpleNamespace(monotonic=lambda: now[0]),
        "_auto_reload_last": {},
        "_AUTO_RELOAD_MIN_FAILURES": 3,
        "_AUTO_RELOAD_COOLDOWN_SEC": 3600,
        "_LOGGER": logging.getLogger("test"),
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<watchdog>", "exec"), ns)
    c = SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="fixture"),
        hass=SimpleNamespace(
            async_create_task=asyncio.run,
            config_entries=SimpleNamespace(async_reload=reload),
        ),
    )
    fail = ns["_note_update_failure"]
    fail(c)
    fail(c)
    assert calls == []
    fail(c)
    assert calls == ["fixture"]
    for _ in range(5):
        fail(c)
    assert len(calls) == 1
    now[0] += 3601
    fail(c)
    assert len(calls) == 2
