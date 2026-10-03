"""PDC WK darten (Alexandra Palace): schema en uitslagen van Wikipedia.

De Wikipedia-pagina heeft een sectie "Schedule" met per dag de sessies
(middag/avond, met begintijd) en per sessie de partijen met uitslag.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .model import Match

_TZ = ZoneInfo("Europe/London")
WK_VENUE = "Alexandra Palace"
WK_CITY = "Londen"
WK_MATCH_SLOT = timedelta(minutes=65)  # geschatte duur per partij in een sessie
WK_SESSION_DURATION = timedelta(hours=4, minutes=30)

# Officiële data per editie (editie = jaar van de finale).
WK_DATES: dict[int, tuple[str, str]] = {
    2026: ("2025-12-11", "2026-01-03"),
    2027: ("2026-12-11", "2027-01-03"),
}

_DAY = re.compile(r"title=\s*(?:[A-Za-z]+,\s*)?(\d{1,2})\s+([A-Za-z]+)")
_SESSION = re.compile(r"(Afternoon|Evening|Morning)\s+session\s*\((\d{1,2}):(\d{2})", re.I)
_ROW = re.compile(r"^\|\s*(\d{1,3})\s*\|\|(.*)$")
_ROUND = re.compile(r"^(?:rowspan\s*=\s*\d+\s*\|)?\s*(\d|QF|SF|F)\s*$", re.I)
_DART_SCORE = re.compile(r"\{\{\s*dart score\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\}\}", re.I)
_PLAIN_SCORE = re.compile(r"^'*\s*(\d+)\s*'*\s*[–-]\s*'*\s*(\d+)")

ROUND_NAMES = {
    "1": "Round 1", "2": "Round 2", "3": "Round 3", "4": "Round 4",
    "QF": "Quarterfinals", "SF": "Semifinals", "F": "Final",
}
SESSION_NL = {"afternoon": "Middagsessie", "evening": "Avondsessie", "morning": "Ochtendsessie"}


@dataclass
class Session:
    """Eén sessie (middag of avond) op één dag."""

    season: int
    start: datetime
    name: str
    matches: list[Match] = field(default_factory=list)

    @property
    def end(self) -> datetime:
        if self.matches:
            last = max(m.start for m in self.matches)
            return max(last + WK_MATCH_SLOT, self.start + timedelta(hours=1))
        return self.start + WK_SESSION_DURATION

    @property
    def rounds(self) -> list[str]:
        seen: list[str] = []
        for m in self.matches:
            if m.round_nl not in seen:
                seen.append(m.round_nl)
        return seen


def _year_for(month: int, season: int) -> int:
    return season - 1 if month >= 7 else season


def _clean_name(cell: str) -> str:
    """Naam uit een cel als "'''[[Ryan Searle (darts player)|Ryan Searle]]''' 91.32"."""
    text = cell.replace("'''", "").replace("''", "")
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # vlaggen e.d.
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+\d+(?:\.\d+)?\s*$", "", text.strip())  # gemiddelde eraf
    text = text.strip(" |")
    if not text or text.lower() in {"tbd", "tba", "v", "vs", "?"}:
        return ""
    return text


def parse_wk_schedule(text: str, season: int) -> list[Match]:
    """Alle partijen uit de sectie Schedule van een WK-pagina."""
    start = re.search(r"^==\s*Schedule\s*==\s*$", text, re.M)
    if not start:
        return []
    end = re.search(r"^==[^=].*==\s*$", text[start.end():], re.M)
    body = text[start.end(): start.end() + end.start() if end else len(text)]

    matches: list[Match] = []
    day: date | None = None
    session_start: datetime | None = None
    session_name = ""
    slot = 0
    current_round = ""
    for line in body.splitlines():
        if "title=" in line and (m := _DAY.search(line)):
            try:
                month = datetime.strptime(m.group(2), "%B").month
                day = date(_year_for(month, season), month, int(m.group(1)))
            except ValueError:
                day = None
            session_start = None
            continue
        if (m := _SESSION.search(line)) and day:
            local = datetime(day.year, day.month, day.day, int(m.group(2)), int(m.group(3)), tzinfo=_TZ)
            session_start = local.astimezone(timezone.utc)
            session_name = SESSION_NL.get(m.group(1).lower(), "Sessie")
            slot = 0
            continue
        row = _ROW.match(line.strip())
        if not row or session_start is None:
            continue
        cells = [c.strip() for c in row.group(2).split("||")]
        if cells and (r := _ROUND.match(cells[0])):
            current_round = r.group(1).upper()
            cells = cells[1:]
        if len(cells) < 3 or not current_round:
            continue
        home, score_cell, away = _clean_name(cells[0]), cells[1], _clean_name(cells[2])
        if not home or not away:
            continue

        hs = as_ = None
        walkover = "w/o" in score_cell.lower() or "walkover" in score_cell.lower()
        if s := _DART_SCORE.search(score_cell):
            hs, as_ = int(s.group(1)), int(s.group(2))
        elif s := _PLAIN_SCORE.match(score_cell):
            hs, as_ = int(s.group(1)), int(s.group(2))

        winner = None
        status = "notstarted"
        if walkover:
            status = "finished"
            winner = home if "'''" in cells[0] else away
        elif hs is not None and as_ is not None and hs != as_:
            status = "finished"
            winner = home if hs > as_ else away

        match = Match(
            id=3_000_000 + season * 1000 + int(row.group(1)),
            season=season,
            start=session_start + WK_MATCH_SLOT * slot,
            home=home,
            away=away,
            home_score=hs,
            away_score=as_,
            status=status,
            round_name=ROUND_NAMES.get(current_round, current_round),
            best_of_legs=None,
            night_number=None,
            winner=winner,
        )
        match.estimated_time = slot > 0
        match.walkover = walkover
        match.competition = "wk"
        match.session_start = session_start
        match.session_name = session_name
        matches.append(match)
        slot += 1
    return matches


def build_sessions(season: int, matches: list[Match]) -> list[Session]:
    """Groepeer partijen per sessie."""
    sessions: dict[datetime, Session] = {}
    for m in sorted(matches, key=lambda x: (x.start, x.id)):
        key = m.session_start or m.start
        if key not in sessions:
            sessions[key] = Session(season, key, m.session_name or "Sessie")
        sessions[key].matches.append(m)
    return sorted(sessions.values(), key=lambda s: s.start)


def wk_target_season(today: date) -> int:
    """Lopende editie: tot half januari de huidige, daarna de volgende."""
    if today.month == 1 and today.day <= 15:
        return today.year
    return today.year + 1


def wk_period(season: int, matches: list[Match]) -> tuple[date | None, date | None]:
    if season in WK_DATES:
        a, b = WK_DATES[season]
        return date.fromisoformat(a), date.fromisoformat(b)
    if matches:
        days = [m.start.astimezone(_TZ).date() for m in matches]
        return min(days), max(days)
    return None, None


def still_in(matches: list[Match]) -> list[str]:
    """Spelers die nog niet zijn uitgeschakeld (alleen zinvol tijdens het WK)."""
    players: set[str] = set()
    out: set[str] = set()
    for m in matches:
        players.update((m.home, m.away))
        if m.status == "finished" and m.winner:
            out.add(m.away if m.winner == m.home else m.home)
    return sorted(players - out)
