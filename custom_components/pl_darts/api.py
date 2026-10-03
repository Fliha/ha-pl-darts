"""Client voor de (onofficiële) SofaScore-API."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from .const import API_BASE, MAX_PAGES, UNIQUE_TOURNAMENT_ID, USER_AGENT
from .model import Match, parse_event

_LOGGER = logging.getLogger(__name__)


class DartsApiError(Exception):
    """De bron gaf een fout of was niet bereikbaar."""


class DartsApi:
    """Haalt seizoenen en wedstrijden op."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> dict | None:
        url = f"{API_BASE}{path}"
        try:
            async with asyncio.timeout(20):
                resp = await self._session.get(
                    url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
                if resp.status == 404:
                    return None  # bv. nog geen komende wedstrijden
                if resp.status != 200:
                    raise DartsApiError(f"{url} gaf HTTP {resp.status}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DartsApiError(f"{url} niet bereikbaar: {err}") from err

    async def seasons(self) -> dict[int, int]:
        """Geef {jaar: seizoen_id}."""
        data = await self._get(f"/unique-tournament/{UNIQUE_TOURNAMENT_ID}/seasons")
        result: dict[int, int] = {}
        for s in (data or {}).get("seasons", []):
            year = str(s.get("year", ""))
            if year.isdigit():
                result[int(year)] = int(s["id"])
        return result

    async def _events(self, season_id: int, direction: str) -> list[Match]:
        matches: list[Match] = []
        for page in range(MAX_PAGES):
            data = await self._get(
                f"/unique-tournament/{UNIQUE_TOURNAMENT_ID}/season/{season_id}"
                f"/events/{direction}/{page}"
            )
            if not data:
                break
            for raw in data.get("events", []):
                match = parse_event(raw)
                if match:
                    matches.append(match)
            if not data.get("hasNextPage"):
                break
        return matches

    async def season_matches(self, season_id: int) -> list[Match]:
        """Alle gespeelde en komende wedstrijden van een seizoen."""
        played = await self._events(season_id, "last")
        upcoming = await self._events(season_id, "next")
        unique = {m.id: m for m in played + upcoming}
        return sorted(unique.values(), key=lambda m: m.start)
