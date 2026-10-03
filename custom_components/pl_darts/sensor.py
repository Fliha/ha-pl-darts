"""Sensoren: volgende avond, volgende partij, live, laatste uitslag en stand."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import DartsConfigEntry, DartsCoordinator, DartsData
from .entity import DartsEntity


def _next_night_value(d: DartsData):
    n = d.next_night(dt_util.utcnow())
    return n.start if n else None


def _next_night_attrs(d: DartsData) -> dict[str, Any]:
    n = d.next_night(dt_util.utcnow())
    if not n:
        return {}
    return {
        "bron_fout": d.source_error,
        "seizoen": n.season,
        "avond": n.title,
        "nummer": n.number,
        "datum": n.day.isoformat(),
        "stad": n.city,
        "zaal": n.venue,
        "land": n.country,
        "indeling_bekend": bool(n.matches),
        "partijen": [m.as_dict() for m in n.matches],
    }


def _next_match_value(d: DartsData):
    m = d.next_match(dt_util.utcnow())
    return m.start if m else None


def _match_attrs(m) -> dict[str, Any]:
    return m.as_dict() if m else {}


def _live_value(d: DartsData) -> str:
    m = d.live_match()
    return m.title if m else "Geen"


def _last_value(d: DartsData) -> str | None:
    m = d.last_match()
    return m.title if m else None


def _leader_value(d: DartsData) -> str | None:
    return d.standings[0]["naam"] if d.standings else None


def _standings_attrs(d: DartsData) -> dict[str, Any]:
    return {
        "bron_fout": d.source_error,
        "seizoen": d.standings_season,
        "voorlopig": d.standings_season == d.season,
        "stand": d.standings,
    }


@dataclass(frozen=True, kw_only=True)
class DartsSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DartsData], Any]
    attrs_fn: Callable[[DartsData], dict[str, Any]]


SENSORS: tuple[DartsSensorDescription, ...] = (
    DartsSensorDescription(
        key="next_night",
        icon="mdi:calendar-star",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_night_value,
        attrs_fn=_next_night_attrs,
    ),
    DartsSensorDescription(
        key="next_match",
        icon="mdi:bullseye-arrow",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_match_value,
        attrs_fn=lambda d: _match_attrs(d.next_match(dt_util.utcnow())),
    ),
    DartsSensorDescription(
        key="live_match",
        icon="mdi:television-play",
        value_fn=_live_value,
        attrs_fn=lambda d: _match_attrs(d.live_match()),
    ),
    DartsSensorDescription(
        key="last_result",
        icon="mdi:scoreboard",
        value_fn=_last_value,
        attrs_fn=lambda d: _match_attrs(d.last_match()),
    ),
    DartsSensorDescription(
        key="standings",
        icon="mdi:trophy",
        value_fn=_leader_value,
        attrs_fn=_standings_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: DartsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DartsSensor(coordinator, desc) for desc in SENSORS)


class DartsSensor(DartsEntity, SensorEntity):
    """Een sensor gevoed door de coördinator."""

    entity_description: DartsSensorDescription

    def __init__(self, coordinator: DartsCoordinator, desc: DartsSensorDescription) -> None:
        super().__init__(coordinator, desc.key, "sensor")
        self.entity_description = desc

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)
