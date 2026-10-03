"""Haalt periodiek de data op en houdt die bij voor alle entiteiten."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import DartsApi, DartsApiError, WikipediaApi
from .const import (
    DOMAIN,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_LIVE,
    SCAN_INTERVAL_MATCHDAY,
    SCAN_INTERVAL_WIKI_MIN,
    SCAN_INTERVAL_WK_ACTIVE,
    SOFASCORE_RETRY,
)
from .model import Match, Night, build_nights, compute_standings, target_season
from .wk import Session, build_sessions, still_in, wk_period, wk_target_season

_LOGGER = logging.getLogger(__name__)

SOURCE_SOFASCORE = "SofaScore"
SOURCE_WIKIPEDIA = "Wikipedia"


@dataclass
class DartsData:
    """Alles wat de entiteiten nodig hebben."""

    season: int
    nights: list[Night]
    matches: list[Match]
    standings: list[dict]
    standings_season: int | None
    previous_matches: list[Match] = field(default_factory=list)
    previous_nights: list[Night] = field(default_factory=list)
    source: str | None = None
    source_error: str | None = None
    wk: "WkData | None" = None

    def next_night(self, now: datetime) -> Night | None:
        return next((n for n in self.nights if n.end > now), None)

    def next_match(self, now: datetime) -> Match | None:
        return next(
            (m for m in self.matches if m.status == "notstarted" and m.start > now),
            None,
        )

    def live_match(self) -> Match | None:
        return next((m for m in self.matches if m.status == "inprogress"), None)

    def last_match(self) -> Match | None:
        done = [m for m in self.matches + self.previous_matches if m.status == "finished"]
        return max(done, key=lambda m: (m.start, m.id)) if done else None


@dataclass
class WkData:
    """Het WK: lopende (of komende) editie en de vorige."""

    season: int
    start: date | None
    end: date | None
    sessions: list[Session]
    matches: list[Match]
    previous_season: int
    previous_sessions: list[Session]
    previous_matches: list[Match]
    error: str | None = None

    def next_session(self, now: datetime) -> Session | None:
        return next((s for s in self.sessions if s.end > now), None)

    def next_match(self, now: datetime) -> Match | None:
        return next(
            (m for m in self.matches if m.status == "notstarted" and m.start > now), None
        )

    def last_match(self) -> Match | None:
        done = [m for m in self.matches + self.previous_matches if m.status == "finished"]
        return max(done, key=lambda m: (m.start, m.id)) if done else None

    @staticmethod
    def champion(matches: list[Match]) -> str | None:
        final = [m for m in matches if m.round_name == "Final" and m.winner]
        return final[0].winner if final else None

    def is_active(self, today: date) -> bool:
        return bool(self.start and self.end and self.start <= today <= self.end)

    def remaining(self) -> list[str]:
        return still_in(self.matches) if self.matches else []


type DartsConfigEntry = ConfigEntry[DartsCoordinator]


class DartsCoordinator(DataUpdateCoordinator[DartsData]):
    """Coördineert updates: eerst SofaScore, anders Wikipedia."""

    def __init__(self, hass: HomeAssistant, entry: DartsConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL_IDLE,
        )
        session = async_get_clientsession(hass)
        self.sofa = DartsApi(session)
        self.wiki = WikipediaApi(session)
        self._sofa_blocked_until: datetime | None = None
        self._prev_cache: dict[str, tuple[int, list[Match]]] = {}
        self._warned: set[str] = set()
        self._wk_prev: tuple[int, list[Match]] | None = None

    async def _from_sofascore(self, season: int) -> tuple[list[Match], list[Match]]:
        seasons = await self.sofa.seasons()
        current = await self.sofa.season_matches(seasons[season]) if season in seasons else []
        prev_year = season - 1
        previous: list[Match] = []
        if prev_year in seasons:
            cached = self._prev_cache.get(SOURCE_SOFASCORE)
            if cached and cached[0] == prev_year:
                previous = cached[1]
            else:
                previous = await self.sofa.season_matches(seasons[prev_year])
                self._prev_cache[SOURCE_SOFASCORE] = (prev_year, previous)
        return current, previous

    async def _from_wikipedia(self, season: int) -> tuple[list[Match], list[Match]]:
        current = await self.wiki.season_matches(season)
        prev_year = season - 1
        cached = self._prev_cache.get(SOURCE_WIKIPEDIA)
        if cached and cached[0] == prev_year:
            previous = cached[1]
        else:
            previous = await self.wiki.season_matches(prev_year)
            self._prev_cache[SOURCE_WIKIPEDIA] = (prev_year, previous)
        return current, previous

    async def _fetch_wk(self) -> WkData:
        today = dt_util.now().date()
        season = wk_target_season(today)
        prev = season - 1
        error = None
        matches: list[Match] = []
        previous: list[Match] = []
        try:
            matches = await self.wiki.wk_matches(season)
            if self._wk_prev and self._wk_prev[0] == prev:
                previous = self._wk_prev[1]
            else:
                previous = await self.wiki.wk_matches(prev)
                self._wk_prev = (prev, previous)
        except DartsApiError as err:
            error = str(err)
            self._warn_once("wk", "WK-data niet beschikbaar: %s", err)
            old = self.data.wk if self.data else None
            if old and old.season == season:
                matches, previous = old.matches, old.previous_matches
        else:
            self._warned.discard("wk")
        start, end = wk_period(season, matches)
        return WkData(
            season=season,
            start=start,
            end=end,
            sessions=build_sessions(season, matches),
            matches=matches,
            previous_season=prev,
            previous_sessions=build_sessions(prev, previous),
            previous_matches=previous,
            error=error,
        )

    def _warn_once(self, key: str, msg: str, *args) -> None:
        if key not in self._warned:
            _LOGGER.warning(msg, *args)
            self._warned.add(key)

    async def _async_update_data(self) -> DartsData:
        now = dt_util.utcnow()
        season = target_season(dt_util.now().date())
        matches: list[Match] = []
        previous: list[Match] = []
        source: str | None = None
        errors: list[str] = []

        if not self._sofa_blocked_until or now >= self._sofa_blocked_until:
            try:
                matches, previous = await self._from_sofascore(season)
                source = SOURCE_SOFASCORE
                self._sofa_blocked_until = None
                self._warned.discard(SOURCE_SOFASCORE)
            except DartsApiError as err:
                errors.append(str(err))
                self._sofa_blocked_until = now + SOFASCORE_RETRY
                self._warn_once(
                    SOURCE_SOFASCORE, "SofaScore niet bruikbaar, verder met Wikipedia: %s", err
                )

        if source is None:
            try:
                matches, previous = await self._from_wikipedia(season)
                source = SOURCE_WIKIPEDIA
                self._warned.discard(SOURCE_WIKIPEDIA)
            except DartsApiError as err:
                errors.append(str(err))
                self._warn_once(
                    SOURCE_WIKIPEDIA, "Ook Wikipedia niet bereikbaar, alleen schema: %s", err
                )
                # Houd vast wat we eerder al hadden.
                old = self.data
                if old and old.season == season:
                    matches, previous, source = old.matches, old.previous_matches, old.source

        nights = build_nights(season, matches)
        prev_season = previous[0].season if previous else season - 1
        previous_nights = build_nights(prev_season, previous)

        standings = compute_standings(matches)
        standings_season: int | None = season
        if not standings and previous:
            # Nieuw seizoen nog niet begonnen: toon de eindstand van vorig jaar.
            standings = compute_standings(previous)
            standings_season = prev_season
        if not standings:
            standings_season = None

        data = DartsData(
            season=season,
            nights=nights,
            matches=matches,
            standings=standings,
            standings_season=standings_season,
            previous_matches=previous,
            previous_nights=previous_nights,
            source=source,
            source_error="; ".join(errors) or None,
            wk=await self._fetch_wk(),
        )
        interval = self._pick_interval(data, now)
        if source != SOURCE_SOFASCORE:
            interval = max(interval, SCAN_INTERVAL_WIKI_MIN)
        if data.wk and data.wk.start and data.wk.end:
            today = dt_util.now().date()
            if data.wk.start - timedelta(days=1) <= today <= data.wk.end:
                interval = min(interval, SCAN_INTERVAL_WK_ACTIVE)
        self.update_interval = interval
        return data

    @staticmethod
    def _pick_interval(data: DartsData, now: datetime) -> timedelta:
        if data.live_match():
            return SCAN_INTERVAL_LIVE
        for night in data.nights:
            if night.start - timedelta(minutes=30) <= now <= night.end:
                return SCAN_INTERVAL_LIVE
            if night.start.date() == now.date():
                return SCAN_INTERVAL_MATCHDAY
        return SCAN_INTERVAL_IDLE
