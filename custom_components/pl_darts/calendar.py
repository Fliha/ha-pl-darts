"""Agenda met elke speelavond en elke partij."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MATCH_DURATION
from .coordinator import DartsConfigEntry, DartsCoordinator
from .entity import DartsEntity
from .model import Match, Night


async def async_setup_entry(
    hass: HomeAssistant, entry: DartsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DartsCalendar(entry.runtime_data)])


def _night_event(night: Night) -> CalendarEvent:
    if night.matches:
        lines = [f"{m.start.astimezone(dt_util.DEFAULT_TIME_ZONE):%H:%M}  {m.round_nl}: {m.title}"
                 for m in night.matches]
        if any(m.estimated_time for m in night.matches):
            lines.append("(tijden per partij zijn geschat)")
        description = "\n".join(lines)
    else:
        description = "Wie tegen wie wordt een paar dagen vooraf bekend. Starttijd is een schatting."
    return CalendarEvent(
        start=night.start,
        end=night.end,
        summary=f"Premier League Darts – {night.title} ({night.city})".replace(" ()", ""),
        description=description,
        location=night.location,
        uid=f"pl_darts_{night.season}_{night.number}",
    )


def _match_event(match: Match) -> CalendarEvent:
    night = match.night
    desc = [match.round_nl]
    if night:
        desc.append(f"{night.title}, {night.location}")
    if match.winner:
        desc.append(f"Winnaar: {match.winner}")
    return CalendarEvent(
        start=match.start,
        end=match.start + MATCH_DURATION,
        summary=f"🎯 {match.title}",
        description="\n".join(d for d in desc if d),
        location=night.location if night else None,
        uid=f"pl_darts_match_{match.id}",
    )


class DartsCalendar(DartsEntity, CalendarEntity):
    """Kalender-entiteit."""

    def __init__(self, coordinator: DartsCoordinator) -> None:
        super().__init__(coordinator, "calendar", "calendar")

    def _all_events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        nights = data.previous_nights + data.nights
        matches = data.previous_matches + data.matches
        events = [_night_event(n) for n in nights]
        events += [_match_event(m) for m in matches]
        return sorted(events, key=lambda e: e.start)

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.utcnow()
        data = self.coordinator.data
        night = data.next_night(now)
        return _night_event(night) if night else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [e for e in self._all_events() if e.end > start_date and e.start < end_date]
