"""Constanten voor de Premier League Darts integratie."""
from __future__ import annotations

from datetime import time, timedelta

DOMAIN = "pl_darts"
NAME = "Premier League Darts"

# Bron voor wedstrijden, tijden en uitslagen (onofficiële SofaScore-API).
# Twee adressen voor dezelfde API; de tweede is wat de website zelf gebruikt.
API_BASES = (
    "https://www.sofascore.com/api/v1",
    "https://api.sofascore.com/api/v1",
)
UNIQUE_TOURNAMENT_ID = 11565  # "Premier League Darts" bij SofaScore
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "Cache-Control": "no-cache",
}
MAX_PAGES = 8

# Ververs-interval: rustig als er niks gebeurt, snel tijdens een speelavond.
SCAN_INTERVAL_IDLE = timedelta(hours=1)
SCAN_INTERVAL_MATCHDAY = timedelta(minutes=10)
SCAN_INTERVAL_LIVE = timedelta(minutes=1)

# Speelavonden beginnen rond 19:00 Britse tijd (20:00 in NL).
NIGHT_TZ = "Europe/London"
NIGHT_START = time(19, 0)
NIGHT_DURATION = timedelta(hours=4, minutes=30)
MATCH_DURATION = timedelta(minutes=25)

# Puntentelling sinds 2022: winnaar 5, verliezend finalist 3,
# verliezende halvefinalisten 2, verliezers kwartfinale 0.
POINTS_WIN = 5
POINTS_RUNNER_UP = 3
POINTS_SEMI = 2
LEAGUE_BEST_OF_LEGS = 11  # play-off wedstrijden zijn langer (19/21 legs)

# Officieel schema per seizoen: (avond, datum, stad, zaal, landcode).
# Avond 17 = play-offs. Bron: PDC, aangekondigd 24 september 2026.
SCHEDULES: dict[int, list[tuple[int, str, str, str, str]]] = {
    2027: [
        (1, "2027-02-04", "Glasgow", "OVO Hydro", "GB"),
        (2, "2027-02-11", "Berlijn", "Uber Arena", "DE"),
        (3, "2027-02-18", "Newcastle", "Utilita Arena", "GB"),
        (4, "2027-02-25", "Belfast", "The O2 Belfast", "GB"),
        (5, "2027-03-04", "Cardiff", "Utilita Arena", "GB"),
        (6, "2027-03-11", "Nottingham", "Motorpoint Arena", "GB"),
        (7, "2027-03-18", "Dublin", "3Arena", "IE"),
        (8, "2027-03-25", "Antwerpen", "AFAS Dome", "BE"),
        (9, "2027-04-01", "Brighton", "Brighton Centre", "GB"),
        (10, "2027-04-08", "Manchester", "AO Arena", "GB"),
        (11, "2027-04-15", "Rotterdam", "Rotterdam Ahoy", "NL"),
        (12, "2027-04-22", "Liverpool", "M&S Bank Arena", "GB"),
        (13, "2027-04-29", "Birmingham", "Utilita Arena", "GB"),
        (14, "2027-05-06", "Leeds", "First Direct Arena", "GB"),
        (15, "2027-05-13", "Aberdeen", "P&J Live", "GB"),
        (16, "2027-05-20", "Sheffield", "Utilita Arena", "GB"),
        (17, "2027-05-27", "Londen", "The O2", "GB"),
    ],
}

ROUND_NL = {
    "Quarterfinals": "Kwartfinale",
    "Semifinals": "Halve finale",
    "Final": "Finale",
}
