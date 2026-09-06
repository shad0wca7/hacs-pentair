"""Pentair button platform.

Buttons cover write-only command transitions that aren't steady states.
For Color Sync that's Hold (`d1=5`, freezes the current animation on its
present color) and Recall (`d1=6`, resumes the last show before Hold).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PentairConfigEntry
from .entity import PentairEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PentairButtonEntityDescription(ButtonEntityDescription):
    """Describes a write-only Pentair command button."""

    field: str
    value: str


_COLOR_SYNC_BUTTONS: list[PentairButtonEntityDescription] = [
    PentairButtonEntityDescription(
        key="pool_lights_hold",
        field="d1",
        value="5",
        translation_key="pool_lights_hold",
        icon="mdi:pause",
    ),
    PentairButtonEntityDescription(
        key="pool_lights_recall",
        field="d1",
        value="6",
        translation_key="pool_lights_recall",
        icon="mdi:play",
    ),
]

_SUPPORTED_DEVICE_TYPES: dict[str, list[PentairButtonEntityDescription]] = {
    "PLC1": _COLOR_SYNC_BUTTONS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PentairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Pentair command buttons for supported device types."""
    coordinator = config_entry.runtime_data
    entities: list[PentairFieldButton] = []
    for device_coordinator in coordinator.device_coordinators:
        data = device_coordinator.get_device_data()
        if not data:
            continue
        for description in _SUPPORTED_DEVICE_TYPES.get(data.get("deviceType"), []):
            entities.append(
                PentairFieldButton(
                    coordinator=device_coordinator,
                    config_entry=config_entry,
                    description=description,
                    device_id=data["deviceId"],
                )
            )
    if entities:
        async_add_entities(entities)


class PentairFieldButton(PentairEntity, ButtonEntity):
    """Button that writes a fixed value to a Pentair field on press."""

    entity_description: PentairButtonEntityDescription

    async def async_press(self) -> None:
        await self.coordinator.async_set_fields(
            {self.entity_description.field: self.entity_description.value}
        )
        await self.coordinator.async_request_refresh()
