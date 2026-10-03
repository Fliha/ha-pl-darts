"""Wedstrijden uit de Wikipedia-pagina van een seizoen halen (reservebron).

Wikipedia heeft geen tijden per partij, alleen de indeling en uitslagen per
avond. Begintijden worden daarom geschat vanaf het begin van de avond.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .const import NIGHT_START, NIGHT_TZ
from .model import Match

_TZ = ZoneInfo(NIGHT_TZ)
_SECTION = re.compile(r"^(={2,4})\s*(.+?)\s*\1\s*$", re.MULTILINE)
_NIGHT_HDR = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s*[–-]\s*Night\s+(\d+)", re.IGNORECASE)
_PLAYOFF_HDR = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s*[–-]\s*Play-?offs", re.IGNORECASE)
_PARAM = re.compile(r"^\|[ \t]*RD(\d)-(team|score)(\d+)[ \t]*=[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_FLAG = re.compile(r"\{\{\s*PDCFlag\s*\|\s*([^|}]+)")
_SCORE = re.compile(r"^'*\s*(\d+)")
_PLAYOFF_SCORED = re.compile(
    r"PDCFlag\s*\|\s*([^|}]+)[^\n]*?\|\|[^\n]*?(\d+)'*\s*[–-]\s*'*(\d+)[^\n]*?\|\|[^\n]*?PDCFlag\s*\|\s*([^|}]+)"
)
_PLAYOFF_OPEN = re.compile(r"PDCFlag\s*\|\s*([^|}]+).*\|\|.*PDCFlag\s*\|\s*([^|}]+)")
_ROUNDS = {1: "Quarterfinals", 2: "Semifinals", 3: "Final"}

# Geschatte begintijd per partij, in minuten na het begin van de avond.
_OFFSETS = {
    ("Quarterfinals", 0): 0, ("Quarterfinals", 1): 25,
    ("Quarterfinals", 2): 50, ("Quarterfinals", 3): 75,
    ("Semifinals", 0): 100, ("Semifinals", 1): 125,
    ("Final", 0): 150,
}


def _night_start(day: date) -> datetime:
    return datetime.combine(day, NIGHT_START, tzinfo=_TZ).astimezone(timezone.utc)


def _parse_day(day: str, month: str, season: int) -> date | None:
    try:
        return datetime.strptime(f"{day} {month} {season}", "%d %B %Y").date()
    except ValueError:
        return None


def _score(raw: str) -> tuple[int | None, bool, bool]:
    """Geeft (score, walkover-winst, afgemeld)."""
    if "w/o" in raw.lower() or "walkover" in raw.lower():
        return None, True, False
    if "efn" in raw.lower() or "withdrew" in raw.lower():
        return None, False, True
    m = _SCORE.match(raw.strip())
    return (int(m.group(1)) if m else None), False, False


def _make(season, night, idx, start, rnd, home, away, hs, as_, walk_home, walk_away, bol):
    winner = None
    status = "notstarted"
    if walk_home or walk_away:
        status, winner = "finished", (home if walk_home else away)
        hs = as_ = None
    elif hs is not None and as_ is not None:
        status = "finished"
        winner = home if hs > as_ else away
    match = Match(
        id=season * 10000 + night * 100 + idx,
        season=season,
        start=start,
        home=home,
        away=away,
        home_score=hs,
        away_score=as_,
        status=status,
        round_name=rnd,
        best_of_legs=bol,
        night_number=night,
        winner=winner,
    )
    match.estimated_time = True
    match.walkover = bool(walk_home or walk_away)
    return match


def _parse_night(body: str, season: int, night: int, day: date) -> list[Match]:
    teams: dict[tuple[int, int], str] = {}
    scores: dict[tuple[int, int], str] = {}
    for rd, kind, pos, value in _PARAM.findall(body):
        key = (int(rd), int(pos))
        if kind == "team":
            flag = _FLAG.search(value)
            if flag and flag.group(1).strip():
                teams[key] = flag.group(1).strip()
        else:
            scores[key] = value

    matches: list[Match] = []
    base = _night_start(day)
    for rd, rnd in _ROUNDS.items():
        for k in range(4 if rd == 1 else 2 if rd == 2 else 1):
            a, b = (rd, 2 * k + 1), (rd, 2 * k + 2)
            if a not in teams or b not in teams:
                continue  # indeling nog niet bekend
            hs, wh, wd_h = _score(scores.get(a, ""))
            as_, wa, wd_a = _score(scores.get(b, ""))
            walk_home = wh or wd_a
            walk_away = wa or wd_h
            start = base + timedelta(minutes=_OFFSETS[(rnd, k)])
            matches.append(
                _make(season, night, rd * 10 + k, start, rnd, teams[a], teams[b],
                      hs, as_, walk_home, walk_away, 11)
            )
    return matches


def _parse_playoffs(body: str, season: int, day: date) -> list[Match]:
    matches: list[Match] = []
    base = _night_start(day)
    rnd, n = "Semifinals", 0
    for line in body.splitlines():
        if "'''Semi-finals'''" in line:
            rnd = "Semifinals"
        elif "'''Final'''" in line:
            rnd = "Final"
        if m := _PLAYOFF_SCORED.search(line):
            home, hs, as_, away = m.group(1).strip(), m.group(2), m.group(3), m.group(4).strip()
        elif m := _PLAYOFF_OPEN.search(line):
            home, hs, as_, away = m.group(1).strip(), None, None, m.group(2).strip()
        else:
            continue
        bol = 19 if rnd == "Semifinals" else 21
        start = base + timedelta(minutes=50 * n)
        matches.append(
            _make(season, 17, 90 + n, start, rnd, home, away,
                  int(hs) if hs else None, int(as_) if as_ else None, False, False, bol)
        )
        n += 1
    return matches


def parse_wikitext(text: str, season: int) -> list[Match]:
    """Alle partijen van een seizoen uit de ruwe wikitekst."""
    heads = list(_SECTION.finditer(text))
    matches: list[Match] = []
    for i, head in enumerate(heads):
        title = head.group(2)
        body = text[head.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if m := _NIGHT_HDR.search(title):
            day = _parse_day(m.group(1), m.group(2), season)
            if day:
                matches += _parse_night(body, season, int(m.group(3)), day)
        elif m := _PLAYOFF_HDR.search(title):
            day = _parse_day(m.group(1), m.group(2), season)
            if day:
                matches += _parse_playoffs(body, season, day)
    return sorted(matches, key=lambda x: (x.start, x.id))
