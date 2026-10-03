from datetime import date, datetime, timezone

from pl_darts.model import build_nights, compute_standings, parse_event, target_season


def ev(id_, ts, home, away, hs, as_, rnd, winner, night=16, season=2026, status="finished", bol=11):
    return {
        "id": id_,
        "startTimestamp": ts,
        "tournament": {"name": f"Premier League, Night {night}"},
        "season": {"year": str(season)},
        "roundInfo": {"name": rnd},
        "status": {"type": status},
        "winnerCode": winner,
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "homeScore": {"current": hs} if hs is not None else {},
        "awayScore": {"current": as_} if as_ is not None else {},
        "bestOfLegs": bol,
    }


# Avond 16 van 2026 (Sheffield), zoals SofaScore hem teruggaf
NIGHT16 = [
    ev(1, 1779387660, "Jonny Clayton", "Stephen Bunting", 3, 6, "Quarterfinals", 2),
    ev(2, 1779389280, "Gerwyn Price", "Gian Van Veen", 6, 2, "Quarterfinals", 1),
    ev(3, 1779390720, "Luke Littler", "Josh Rock", 6, 5, "Quarterfinals", 1),
    ev(4, 1779392520, "Luke Humphries", "Michael van Gerwen", 6, 5, "Quarterfinals", 1),
    ev(5, 1779394000, "Stephen Bunting", "Gerwyn Price", 6, 4, "Semifinals", 1),
    ev(6, 1779396000, "Luke Littler", "Luke Humphries", 6, 3, "Semifinals", 1),
    ev(7, 1779398000, "Luke Littler", "Stephen Bunting", 6, 2, "Final", 1),
]


def test_parse_event():
    m = parse_event(NIGHT16[0])
    assert m.home == "Jonny Clayton" and m.away == "Stephen Bunting"
    assert m.winner == "Stephen Bunting"
    assert m.title == "Jonny Clayton 3–6 Stephen Bunting"
    assert m.night_number == 16 and m.season == 2026
    assert m.start == datetime(2026, 5, 21, 18, 21, tzinfo=timezone.utc)
    assert parse_event({"foo": 1}) is None


def test_upcoming_has_no_winner_or_score():
    m = parse_event(ev(9, 1779387660, "A", "B", None, None, "Quarterfinals", None, status="notstarted"))
    assert m.winner is None and m.title == "A – B"


def test_standings_points():
    rows = compute_standings([parse_event(e) for e in NIGHT16])
    pts = {r["naam"]: r["punten"] for r in rows}
    assert pts["Luke Littler"] == 5
    assert pts["Stephen Bunting"] == 3
    assert pts["Gerwyn Price"] == 2 and pts["Luke Humphries"] == 2
    assert pts["Josh Rock"] == 0
    assert rows[0]["naam"] == "Luke Littler" and rows[0]["avonden_gewonnen"] == 1
    assert rows[0]["legsaldo"] == (6 + 6 + 6) - (5 + 3 + 2)
    assert len(rows) == 8


def test_playoff_matches_do_not_count():
    playoff = parse_event(ev(20, 1779990000, "Luke Littler", "Gerwyn Price", 10, 3, "Final", 1, night=17, bol=21))
    assert not playoff.is_league
    assert compute_standings([playoff]) == []


def test_schedule_without_matches():
    nights = build_nights(2027, [])
    assert len(nights) == 17
    first = nights[0]
    assert first.city == "Glasgow" and first.venue == "OVO Hydro"
    # 19:00 in Glasgow (wintertijd) = 19:00 UTC = 20:00 in Nederland
    assert first.start == datetime(2027, 2, 4, 19, 0, tzinfo=timezone.utc)
    rotterdam = nights[10]
    # zomertijd: 19:00 BST = 18:00 UTC
    assert rotterdam.city == "Rotterdam" and rotterdam.start.hour == 18
    assert nights[-1].title == "Play-offs"


def test_matches_attach_to_scheduled_night():
    # 4 februari 2027, 19:05 UTC
    m = parse_event(ev(30, int(datetime(2027, 2, 4, 19, 5, tzinfo=timezone.utc).timestamp()),
                       "Luke Littler", "Luke Humphries", None, None, "Quarterfinals", None,
                       night=1, season=2027, status="notstarted"))
    nights = build_nights(2027, [m])
    assert nights[0].matches == [m]
    assert m.night.venue == "OVO Hydro"
    assert nights[0].start == m.start


def test_target_season():
    assert target_season(date(2026, 10, 3)) == 2027
    assert target_season(date(2027, 3, 1)) == 2027


# --- Wikipedia als reservebron -------------------------------------------
from pathlib import Path

from pl_darts.wiki import parse_wikitext

WIKI_2026 = (Path(__file__).parent / "fixtures" / "wikipedia_2026.txt").read_text()


def test_wikipedia_full_season_matches_official_table():
    """Eindstand 2026 volgens Wikipedia: punten en volgorde moeten kloppen."""
    matches = parse_wikitext(WIKI_2026, 2026)
    assert len(matches) == 16 * 7 + 3
    rows = compute_standings(matches)
    got = [(r["naam"], r["punten"], r["avonden_gewonnen"]) for r in rows]
    assert got[:7] == [
        ("Luke Littler", 43, 6),
        ("Jonny Clayton", 34, 4),
        ("Luke Humphries", 27, 1),
        ("Gerwyn Price", 26, 2),
        ("Stephen Bunting", 18, 2),
        ("Michael van Gerwen", 18, 1),
        ("Gian van Veen", 18, 0),
    ]
    by_name = {r["naam"]: r for r in rows}
    # walkovers tellen niet als gespeelde partij (zelfde als Wikipedia)
    assert by_name["Luke Littler"]["partijen_gespeeld"] == 34
    assert by_name["Luke Littler"]["partijen_gewonnen"] == 24
    assert by_name["Michael van Gerwen"]["partijen_gespeeld"] == 25
    assert by_name["Gian van Veen"]["partijen_gespeeld"] == 27
    assert by_name["Jonny Clayton"]["legsaldo"] == 15


def test_wikipedia_walkover_and_playoffs():
    matches = parse_wikitext(WIKI_2026, 2026)
    wo = [m for m in matches if m.walkover]
    assert {(m.night_number, m.winner) for m in wo} == {
        (3, "Luke Littler"),
        (7, "Michael van Gerwen"),
    }
    final = [m for m in matches if m.night_number == 17 and m.round_name == "Final"][0]
    assert (final.home, final.home_score, final.away_score, final.winner) == (
        "Luke Littler", 11, 10, "Luke Littler"
    )
    assert not final.is_league


def test_wikipedia_draw_known_but_not_played():
    text = """===4 February – Night 1===
| RD1-team1   = {{PDCFlag|Luke Littler|avg=}}
| RD1-score1  =
| RD1-team2   = {{PDCFlag|Luke Humphries|avg=}}
| RD1-score2  =
| RD2-team1   =
| RD2-score1  =
"""
    matches = parse_wikitext(text, 2027)
    assert len(matches) == 1
    m = matches[0]
    assert m.status == "notstarted" and m.winner is None
    assert m.estimated_time
    assert m.start == datetime(2027, 2, 4, 19, 0, tzinfo=timezone.utc)


# --- WK -------------------------------------------------------------------
from pl_darts.wk import build_sessions, parse_wk_schedule, still_in, wk_period, wk_target_season

WK_2026 = (Path(__file__).parent / "fixtures" / "wikipedia_wk_2026.txt").read_text()


def test_wk_schedule_parsing():
    ms = parse_wk_schedule(WK_2026, 2026)
    assert len(ms) == 16
    first = ms[0]
    assert (first.home, first.away, first.winner) == ("Kim Huybrechts", "Arno Merk", "Arno Merk")
    assert first.round_nl == "Ronde 1" and first.session_name == "Avondsessie"
    # december hoort bij het jaar vóór de finale
    assert first.start == datetime(2025, 12, 11, 19, 0, tzinfo=timezone.utc)
    assert not first.estimated_time and ms[1].estimated_time
    # [[Link|Naam]] en namen zonder link
    names = {m.home for m in ms} | {m.away for m in ms}
    assert "Ryan Searle" in names and "David Davies" in names and "Michael Smith" in names
    final = ms[-1]
    assert final.round_name == "Final" and final.title == "Luke Littler 7–1 Gian van Veen"
    assert final.start == datetime(2026, 1, 3, 20, 0, tzinfo=timezone.utc)


def test_wk_walkover_and_sessions():
    ms = parse_wk_schedule(WK_2026, 2026)
    wo = [m for m in ms if m.walkover][0]
    assert wo.winner == "Jonny Clayton" and wo.status == "finished"
    sessions = build_sessions(2026, ms)
    assert len(sessions) == 7
    jan1 = [s for s in sessions if s.start.date().isoformat() == "2026-01-01"]
    assert [s.name for s in jan1] == ["Middagsessie", "Avondsessie"]
    assert jan1[0].rounds == ["Kwartfinale"]


def test_wk_dates_and_remaining():
    assert wk_target_season(date(2026, 10, 3)) == 2027
    assert wk_target_season(date(2027, 1, 2)) == 2027
    assert wk_target_season(date(2027, 2, 1)) == 2028
    assert wk_period(2027, []) == (date(2026, 12, 11), date(2027, 1, 3))
    ms = parse_wk_schedule(WK_2026, 2026)
    remaining = still_in(ms)
    assert "Luke Littler" in remaining
    assert "Gian van Veen" not in remaining and "Kim Huybrechts" not in remaining


def test_wk_unknown_players_skipped_and_unplayed():
    text = """==Schedule==
{{hidden begin|title=Friday, 11 December}}
|+ '''Evening session (19:00 [[Greenwich Mean Time|GMT]])'''
| 01 || rowspan=4| 1 || [[Luke Littler]] || v || [[Some Qualifier]] ||
| 02 || TBD || v || TBD ||
==Draw==
"""
    ms = parse_wk_schedule(text, 2027)
    assert len(ms) == 1
    assert ms[0].status == "notstarted" and ms[0].winner is None
    assert ms[0].start == datetime(2026, 12, 11, 19, 0, tzinfo=timezone.utc)
