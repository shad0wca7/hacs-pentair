"""Pentair select platform.

Color Sync's `d1` field is an enum (0-13) selecting one of 12 named scenes
(5 solid colors + 7 shows).  Values 5 (Hold) and 6 (Recall) are skipped
here — they're command-style transitions, not steady states, and surface as
button entities instead (see `button.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PentairConfigEntry
from .entity import PentairEntity
from .helpers import get_field_value

_LOGGER = logging.getLogger(__name__)

# d1 -> display name.  Empirically mapped by setting each value and reading
# the canonical name back from the Pentair Home iOS app (2026-05-18 / PLC1
# fwVersion 1.0).  Writing 14 is silently clamped to 13 by the device so
# don't expose it.
COLOR_SYNC_MODES: dict[int, str] = {
    0: "Red",
    1: "White",
    2: "Magenta",
    3: "Green",
    4: "Blue",
    # 5 = Hold, 6 = Recall — exposed via button.py
    7: "SAm",
    8: "Party",
    9: "Romance",
    10: "Caribbean",
    11: "American",
    12: "Sunset",
    13: "Royal",
}
_NAME_TO_VALUE = {v: k for k, v in COLOR_SYNC_MODES.items()}


@dataclass(frozen=True, kw_only=True)
class PentairSelectEntityDescription(SelectEntityDescription):
    """Entity description that carries the field + value/option mapping."""

    field: str
    value_to_option: dict[int, str]


_COLOR_SYNC_MODE = PentairSelectEntityDescription(
    key="d1",
    field="d1",
    translation_key="pool_lights_mode",
    icon="mdi:palette",
    value_to_option=COLOR_SYNC_MODES,
)

_SUPPORTED_DEVICE_TYPES: dict[str, list[PentairSelectEntityDescription]] = {
    "PLC1": [_COLOR_SYNC_MODE],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PentairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Pentair select entities for supported device types."""
    coordinator = config_entry.runtime_data
    entities: list[PentairFieldSelect] = []
    for device_coordinator in coordinator.device_coordinators:
        data = device_coordinator.get_device_data()
        if not data:
            continue
        for description in _SUPPORTED_DEVICE_TYPES.get(data.get("deviceType"), []):
            entities.append(
                PentairFieldSelect(
                    coordinator=device_coordinator,
                    config_entry=config_entry,
                    description=description,
                    device_id=data["deviceId"],
                )
            )
    if entities:
        async_add_entities(entities)


class PentairFieldSelect(PentairEntity, SelectEntity):
    """Select backed by a single integer-coded Pentair field."""

    entity_description: PentairSelectEntityDescription

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._name_to_value = {
            v: k for k, v in self.entity_description.value_to_option.items()
        }
        self._attr_options = list(self.entity_description.value_to_option.values())

    @property
    def current_option(self) -> str | None:
        """Map the live field value back to its display name."""
        if (data := self.get_device()) is None:
            return None
        raw = get_field_value(self.entity_description.field, data)
        try:
            return self.entity_description.value_to_option.get(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        if (value := self._name_to_value.get(option)) is None:
            raise ValueError(f"unknown option for {self.entity_id}: {option!r}")
        await self.coordinator.async_set_fields(
            {self.entity_description.field: str(value)}
        )
        await self.coordinator.async_request_refresh()
