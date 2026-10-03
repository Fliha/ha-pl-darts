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
from datetime import datetime, time
from zoneinfo import ZoneInfo

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
        "bron": d.source,
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
        "bron": d.source,
        "bron_fout": d.source_error,
        "seizoen": d.standings_season,
        "voorlopig": d.standings_season == d.season,
        "stand": d.standings,
    }


# ---- WK ---------------------------------------------------------------

def _wk_status(d: DartsData) -> str | None:
    wk = d.wk
    if wk is None:
        return None
    today = dt_util.now().date()
    champ = wk.champion(wk.matches)
    if champ:
        return f"Wereldkampioen: {champ}"
    if wk.is_active(today):
        last = next((m for m in reversed(wk.matches) if m.status == "finished"), None)
        return f"Bezig: {last.round_nl}" if last else "Bezig"
    if wk.start and today < wk.start:
        return f"Begint {wk.start.day} {_MONTHS[wk.start.month]}"
    return "Afgelopen"


_MONTHS = ["", "januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"]


def _wk_status_attrs(d: DartsData) -> dict[str, Any]:
    wk = d.wk
    if wk is None:
        return {}
    played = [m for m in wk.matches if m.status == "finished"]
    return {
        "editie": f"{wk.season - 1}/{str(wk.season)[-2:]}",
        "start": wk.start.isoformat() if wk.start else None,
        "finale": wk.end.isoformat() if wk.end else None,
        "zaal": "Alexandra Palace",
        "stad": "Londen",
        "programma_bekend": bool(wk.matches),
        "partijen_gespeeld": len(played),
        "partijen_totaal": len(wk.matches),
        "nog_in_toernooi": wk.remaining() if played else [],
        "kampioen": wk.champion(wk.matches),
        "vorige_kampioen": wk.champion(wk.previous_matches),
        "bron_fout": wk.error,
    }


def _wk_next_session_value(d: DartsData):
    wk = d.wk
    if wk is None:
        return None
    s = wk.next_session(dt_util.utcnow())
    if s:
        return s.start
    if wk.start and not wk.sessions and dt_util.now().date() <= wk.start:
        # Schema nog niet bekend: eerste avond begint traditioneel om 19:00 Britse tijd.
        return dt_util.as_utc(
            datetime.combine(wk.start, time(19, 0), tzinfo=ZoneInfo("Europe/London"))
        )
    return None


def _wk_next_session_attrs(d: DartsData) -> dict[str, Any]:
    wk = d.wk
    if wk is None:
        return {}
    s = wk.next_session(dt_util.utcnow())
    if not s:
        return {"programma_bekend": False, "tijd_geschat": True}
    return {
        "programma_bekend": True,
        "sessie": s.name,
        "rondes": s.rounds,
        "partijen": [m.as_dict() for m in s.matches],
    }


@dataclass(frozen=True, kw_only=True)
class DartsSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DartsData], Any]
    attrs_fn: Callable[[DartsData], dict[str, Any]]
    device: str = "pl"


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
    DartsSensorDescription(
        key="wk_status",
        icon="mdi:trophy-variant",
        device="wk",
        value_fn=_wk_status,
        attrs_fn=_wk_status_attrs,
    ),
    DartsSensorDescription(
        key="wk_next_session",
        icon="mdi:calendar-star",
        device_class=SensorDeviceClass.TIMESTAMP,
        device="wk",
        value_fn=_wk_next_session_value,
        attrs_fn=_wk_next_session_attrs,
    ),
    DartsSensorDescription(
        key="wk_next_match",
        icon="mdi:bullseye-arrow",
        device_class=SensorDeviceClass.TIMESTAMP,
        device="wk",
        value_fn=lambda d: (m.start if d.wk and (m := d.wk.next_match(dt_util.utcnow())) else None),
        attrs_fn=lambda d: _match_attrs(d.wk.next_match(dt_util.utcnow())) if d.wk else {},
    ),
    DartsSensorDescription(
        key="wk_last_result",
        icon="mdi:scoreboard",
        device="wk",
        value_fn=lambda d: (m.title if d.wk and (m := d.wk.last_match()) else None),
        attrs_fn=lambda d: _match_attrs(d.wk.last_match()) if d.wk else {},
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
        super().__init__(coordinator, desc.key, "sensor", device=desc.device)
        self.entity_description = desc

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)
