"""Datamodel en rekenwerk, los van Home Assistant (dus makkelijk te testen)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .const import (
    LEAGUE_BEST_OF_LEGS,
    NIGHT_DURATION,
    NIGHT_START,
    NIGHT_TZ,
    POINTS_RUNNER_UP,
    POINTS_SEMI,
    POINTS_WIN,
    ROUND_NL,
    SCHEDULES,
)

_NIGHT_RE = re.compile(r"night\s*(\d+)", re.IGNORECASE)
_TZ = ZoneInfo(NIGHT_TZ)


@dataclass
class Night:
    """Eén speelavond."""

    season: int
    number: int
    day: date
    city: str
    venue: str
    country: str
    matches: list["Match"] = field(default_factory=list)

    @property
    def is_playoffs(self) -> bool:
        return self.number >= 17

    @property
    def title(self) -> str:
        return "Play-offs" if self.is_playoffs else f"Avond {self.number}"

    @property
    def start(self) -> datetime:
        if self.matches:
            return min(m.start for m in self.matches)
        return datetime.combine(self.day, NIGHT_START, tzinfo=_TZ).astimezone(
            timezone.utc
        )

    @property
    def end(self) -> datetime:
        return self.start + NIGHT_DURATION

    @property
    def location(self) -> str:
        return f"{self.venue}, {self.city}" if self.venue else self.city


@dataclass
class Match:
    """Eén partij tussen twee spelers."""

    id: int
    season: int
    start: datetime
    home: str
    away: str
    home_score: int | None
    away_score: int | None
    status: str  # notstarted | inprogress | finished | postponed | canceled
    round_name: str
    best_of_legs: int | None
    night_number: int | None
    winner: str | None = None
    night: Night | None = None

    @property
    def round_nl(self) -> str:
        return ROUND_NL.get(self.round_name, self.round_name or "")

    @property
    def is_league(self) -> bool:
        return (self.best_of_legs or LEAGUE_BEST_OF_LEGS) <= LEAGUE_BEST_OF_LEGS

    @property
    def score(self) -> str:
        if self.home_score is None or self.away_score is None:
            return ""
        return f"{self.home_score}–{self.away_score}"

    @property
    def title(self) -> str:
        if self.status in ("finished", "inprogress") and self.score:
            return f"{self.home} {self.score} {self.away}"
        return f"{self.home} – {self.away}"

    def as_dict(self) -> dict:
        night = self.night
        return {
            "speler_1": self.home,
            "speler_2": self.away,
            "start": self.start.isoformat(),
            "ronde": self.round_nl,
            "stand": self.score,
            "status": self.status,
            "winnaar": self.winner,
            "avond": night.title if night else None,
            "stad": night.city if night else None,
            "zaal": night.venue if night else None,
        }


def parse_event(raw: dict) -> Match | None:
    """Zet een SofaScore-event om naar een Match."""
    try:
        start = datetime.fromtimestamp(int(raw["startTimestamp"]), timezone.utc)
        home = raw["homeTeam"]["name"]
        away = raw["awayTeam"]["name"]
    except (KeyError, TypeError, ValueError):
        return None

    status = (raw.get("status") or {}).get("type", "notstarted")
    hs = (raw.get("homeScore") or {}).get("current")
    as_ = (raw.get("awayScore") or {}).get("current")
    winner_code = raw.get("winnerCode")
    winner = {1: home, 2: away}.get(winner_code) if status == "finished" else None

    season = (raw.get("season") or {}).get("year")
    tname = (raw.get("tournament") or {}).get("name", "")
    m = _NIGHT_RE.search(tname)
    return Match(
        id=int(raw.get("id", 0)),
        season=int(season) if season and str(season).isdigit() else start.year,
        start=start,
        home=home,
        away=away,
        home_score=hs if isinstance(hs, int) else None,
        away_score=as_ if isinstance(as_, int) else None,
        status=status,
        round_name=(raw.get("roundInfo") or {}).get("name", ""),
        best_of_legs=raw.get("bestOfLegs"),
        night_number=int(m.group(1)) if m else None,
        winner=winner,
    )


def build_nights(season: int, matches: list[Match]) -> list[Night]:
    """Combineer het vaste schema met de wedstrijden die al bekend zijn."""
    nights: dict[int, Night] = {
        n: Night(season, n, date.fromisoformat(d), city, venue, cc)
        for n, d, city, venue, cc in SCHEDULES.get(season, [])
    }
    by_date = {night.day: night for night in nights.values()}

    for match in sorted(matches, key=lambda x: x.start):
        if match.season != season:
            continue
        local_day = match.start.astimezone(_TZ).date()
        night = by_date.get(local_day)
        if night is None and match.night_number in nights:
            night = nights[match.night_number]
        if night is None:
            # Avond niet in het vaste schema: maak hem aan zonder zaal.
            number = match.night_number or (17 if not match.is_league else 0)
            night = nights.get(number) or Night(
                season, number, local_day, "", "", ""
            )
            nights[number] = night
            by_date[local_day] = night
        match.night = night
        night.matches.append(match)

    return sorted(nights.values(), key=lambda n: n.day)


def compute_standings(matches: list[Match]) -> list[dict]:
    """Bereken de stand: punten, dan gewonnen avonden, dan gewonnen partijen."""
    table: dict[str, dict] = {}

    def row(name: str) -> dict:
        return table.setdefault(
            name,
            {
                "naam": name,
                "punten": 0,
                "avonden_gewonnen": 0,
                "partijen_gewonnen": 0,
                "partijen_gespeeld": 0,
                "legs_voor": 0,
                "legs_tegen": 0,
            },
        )

    for m in matches:
        if m.status != "finished" or not m.is_league or not m.winner:
            continue
        loser = m.away if m.winner == m.home else m.home
        w, l = row(m.winner), row(loser)
        w["partijen_gewonnen"] += 1
        w["partijen_gespeeld"] += 1
        l["partijen_gespeeld"] += 1
        if m.home_score is not None and m.away_score is not None:
            hs, as_ = m.home_score, m.away_score
            row(m.home)["legs_voor"] += hs
            row(m.home)["legs_tegen"] += as_
            row(m.away)["legs_voor"] += as_
            row(m.away)["legs_tegen"] += hs
        if m.round_name == "Final":
            w["punten"] += POINTS_WIN
            w["avonden_gewonnen"] += 1
            l["punten"] += POINTS_RUNNER_UP
        elif m.round_name == "Semifinals":
            l["punten"] += POINTS_SEMI

    rows = sorted(
        table.values(),
        key=lambda r: (
            -r["punten"],
            -r["avonden_gewonnen"],
            -r["partijen_gewonnen"],
            -(r["legs_voor"] - r["legs_tegen"]),
            r["naam"],
        ),
    )
    for pos, r in enumerate(rows, start=1):
        r["positie"] = pos
        r["legsaldo"] = r["legs_voor"] - r["legs_tegen"]
    return rows


def target_season(today: date) -> int:
    """Seizoen waar we naar kijken: na juni telt het volgende jaar."""
    return today.year if today.month <= 6 else today.year + 1
