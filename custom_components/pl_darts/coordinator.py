"""Haalt periodiek de data op en houdt die bij voor alle entiteiten."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import DartsApi, DartsApiError
from .const import (
    DOMAIN,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_LIVE,
    SCAN_INTERVAL_MATCHDAY,
)
from .model import Match, Night, build_nights, compute_standings, target_season

_LOGGER = logging.getLogger(__name__)


@dataclass
class DartsData:
    """Alles wat de entiteiten nodig hebben."""

    season: int
    nights: list[Night]
    matches: list[Match]
    standings: list[dict]
    standings_season: int | None
    previous_matches: list[Match] = field(default_factory=list)
    source_error: str | None = None

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
        return max(done, key=lambda m: m.start) if done else None


type DartsConfigEntry = ConfigEntry[DartsCoordinator]


class DartsCoordinator(DataUpdateCoordinator[DartsData]):
    """Coördineert updates."""

    def __init__(self, hass: HomeAssistant, entry: DartsConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL_IDLE,
        )
        self.api = DartsApi(async_get_clientsession(hass))
        self._prev_cache: tuple[int, list[Match]] | None = None
        self._warned = False

    async def _async_update_data(self) -> DartsData:
        now = dt_util.utcnow()
        season = target_season(dt_util.now().date())
        source_error: str | None = None
        matches: list[Match] = []
        previous: list[Match] = []
        try:
            seasons = await self.api.seasons()
            if season in seasons:
                matches = await self.api.season_matches(seasons[season])
            older = [y for y in seasons if y < season]
            if older:
                prev_year = max(older)
                if self._prev_cache and self._prev_cache[0] == prev_year:
                    previous = self._prev_cache[1]
                else:
                    previous = await self.api.season_matches(seasons[prev_year])
                    self._prev_cache = (prev_year, previous)
        except DartsApiError as err:
            # Bron niet bereikbaar: val terug op wat we al hadden, of alleen het
            # vaste schema. De integratie blijft dan gewoon werken.
            source_error = str(err)
            if not self._warned:
                _LOGGER.warning("Wedstrijddata niet beschikbaar, alleen schema: %s", err)
                self._warned = True
            old = self.data
            if old and old.season == season:
                matches = old.matches
                previous = old.previous_matches
            elif self._prev_cache:
                previous = self._prev_cache[1]
        else:
            if self._warned:
                _LOGGER.info("Wedstrijddata weer beschikbaar")
            self._warned = False

        nights = build_nights(season, matches)
        standings = compute_standings(matches)
        standings_season: int | None = season
        if not standings and previous:
            # Nieuw seizoen nog niet begonnen: toon de eindstand van vorig jaar.
            standings = compute_standings(previous)
            standings_season = previous[0].season
        if not standings:
            standings_season = None

        data = DartsData(
            season, nights, matches, standings, standings_season, previous, source_error
        )
        interval = self._pick_interval(data, now)
        if source_error:
            interval = max(interval, timedelta(minutes=15))  # bron niet bestoken
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
