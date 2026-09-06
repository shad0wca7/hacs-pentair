"""Pentair switch platform.

Currently scoped to Color Sync (`deviceType == "PLC1"`), where field `d13`
is a U8 on/off flag (`"0"` / `"1"`).  Adding more switchable devices is a
matter of expanding `_SUPPORTED_DEVICE_TYPES` and the matching descriptions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PentairConfigEntry
from .entity import PentairEntity
from .helpers import get_field_value

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PentairSwitchEntityDescription(SwitchEntityDescription):
    """Entity description with the field key + value mapping."""

    field: str
    on_value: str = "1"
    off_value: str = "0"
    is_on_fn: Callable[[Any], bool] | None = None


_COLOR_SYNC_SWITCH = PentairSwitchEntityDescription(
    key="d13",
    field="d13",
    translation_key="pool_lights",
    icon="mdi:pool",
)

# Map deviceType -> list of switch descriptions to instantiate.
_SUPPORTED_DEVICE_TYPES: dict[str, list[PentairSwitchEntityDescription]] = {
    "PLC1": [_COLOR_SYNC_SWITCH],
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PentairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Pentair switch entities for supported device types."""
    coordinator = config_entry.runtime_data
    entities: list[PentairFieldSwitch] = []
    for device_coordinator in coordinator.device_coordinators:
        data = device_coordinator.get_device_data()
        if not data:
            continue
        for description in _SUPPORTED_DEVICE_TYPES.get(data.get("deviceType"), []):
            entities.append(
                PentairFieldSwitch(
                    coordinator=device_coordinator,
                    config_entry=config_entry,
                    description=description,
                    device_id=data["deviceId"],
                )
            )
    if entities:
        async_add_entities(entities)


class PentairFieldSwitch(PentairEntity, SwitchEntity):
    """Switch backed by a single string-valued Pentair field."""

    entity_description: PentairSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return whether the device is on (field == on_value)."""
        if (data := self.get_device()) is None:
            return None
        return get_field_value(self.entity_description.field, data) == (
            self.entity_description.on_value
        )

    async def async_turn_on(self, **_: Any) -> None:
        await self._write(self.entity_description.on_value)

    async def async_turn_off(self, **_: Any) -> None:
        await self._write(self.entity_description.off_value)

    async def _write(self, value: str) -> None:
        await self.coordinator.async_set_fields({self.entity_description.field: value})
        # Optimistic state — refresh confirms.  Update_interval is 30s, so
        # explicitly requesting a refresh keeps the UI snappy.
        await self.coordinator.async_request_refresh()
