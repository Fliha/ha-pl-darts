"""Agenda met elke speelavond en elke partij."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MATCH_DURATION
from .coordinator import DartsConfigEntry, DartsCoordinator
from .entity import DartsEntity
from .model import Match, Night
from .wk import WK_CITY, WK_VENUE, Session


async def async_setup_entry(
    hass: HomeAssistant, entry: DartsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DartsCalendar(entry.runtime_data), WkCalendar(entry.runtime_data)])


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


WK_LOCATION = f"{WK_VENUE}, {WK_CITY}"


def _session_event(session: Session) -> CalendarEvent:
    lines = [
        f"{m.start.astimezone(dt_util.DEFAULT_TIME_ZONE):%H:%M}  {m.round_nl}: {m.title}"
        for m in session.matches
    ]
    if any(m.estimated_time for m in session.matches):
        lines.append("(alleen de eerste partij heeft een vaste begintijd)")
    rounds = ", ".join(session.rounds)
    return CalendarEvent(
        start=session.start,
        end=session.end,
        summary=f"WK Darts – {session.name}" + (f" ({rounds})" if rounds else ""),
        description="\n".join(lines),
        location=WK_LOCATION,
        uid=f"pl_darts_wk_{session.season}_{session.start:%Y%m%d%H%M}",
    )


def _wk_match_event(match: Match) -> CalendarEvent:
    desc = [match.round_nl, match.session_name]
    if match.winner:
        desc.append(f"Winnaar: {match.winner}")
    return CalendarEvent(
        start=match.start,
        end=match.start + timedelta(minutes=60),
        summary=f"🎯 WK: {match.title}",
        description="\n".join(d for d in desc if d),
        location=WK_LOCATION,
        uid=f"pl_darts_wk_match_{match.id}",
    )


class WkCalendar(DartsEntity, CalendarEntity):
    """Agenda met de WK-sessies en -partijen."""

    def __init__(self, coordinator: DartsCoordinator) -> None:
        super().__init__(coordinator, "wk_calendar", "calendar", device="wk")

    def _all_events(self) -> list[CalendarEvent]:
        wk = self.coordinator.data.wk
        if wk is None:
            return []
        events: list[CalendarEvent] = []
        for sessions, matches in (
            (wk.previous_sessions, wk.previous_matches),
            (wk.sessions, wk.matches),
        ):
            events += [_session_event(s) for s in sessions]
            events += [_wk_match_event(m) for m in matches]
        if not wk.sessions and wk.start and wk.end:
            # Programma nog niet bekend: het hele toernooi als één afspraak.
            events.append(
                CalendarEvent(
                    start=wk.start,
                    end=wk.end + timedelta(days=1),
                    summary=f"PDC WK Darts {wk.season - 1}/{str(wk.season)[-2:]}",
                    description="Het speelschema per sessie volgt zodra de loting bekend is.",
                    location=WK_LOCATION,
                    uid=f"pl_darts_wk_{wk.season}_toernooi",
                )
            )
        return sorted(events, key=lambda e: _sort_key(e.start))

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.utcnow()
        for e in self._all_events():
            end = e.end if isinstance(e.end, datetime) else dt_util.start_of_local_day(e.end)
            if end > now:
                return e
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        out = []
        for e in self._all_events():
            s = e.start if isinstance(e.start, datetime) else dt_util.start_of_local_day(e.start)
            en = e.end if isinstance(e.end, datetime) else dt_util.start_of_local_day(e.end)
            if en > start_date and s < end_date:
                out.append(e)
        return out


def _sort_key(value) -> datetime:
    return value if isinstance(value, datetime) else dt_util.start_of_local_day(value)
