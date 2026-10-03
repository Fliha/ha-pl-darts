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
