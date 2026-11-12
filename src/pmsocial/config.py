"""Project-wide paths, API endpoints, and NBA team metadata."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
# public.api.bsky.app returns 403 for unauthenticated search (verified 2026-10-27);
# api.bsky.app serves page 1 of searchPosts without login (cursor requests are 403).
BSKY_SEARCH = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
GDELT_FILES = "https://data.gdeltproject.org/gdeltv2"
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

# Milestone II in-game window per game: [game_start - BEFORE, game_start + AFTER), 1-minute rows.
INGAME_BEFORE_MIN = 120
INGAME_AFTER_MIN = 210
PILOT_GAMES = ("nba-cle-phi-2026-10-22", "nba-nyk-bos-2026-10-23", "nba-mem-uta-2026-10-26")

# Pilot sample window: opening week of the 2026-27 NBA regular season.
SAMPLE_GAME_DATES = ("2026-10-21", "2026-10-26")
MIN_MONEYLINE_VOLUME = 250_000
MIN_PREGAME_PRICE_HOURS = 48
N_GAMES = 8
# Hours of social/news history collected before market open, used as the
# baseline for abnormal-attention measures.
BASELINE_HOURS = 72

# abbr -> (full name, nickname, bluesky query).
# Nicknames that are common English words use the quoted full name to avoid
# unrelated posts ("heat wave", "magic trick", "kings of ...").
TEAMS = {
    "atl": ("Atlanta Hawks", "Hawks", '"Atlanta Hawks"'),
    "bos": ("Boston Celtics", "Celtics", "Celtics"),
    "bkn": ("Brooklyn Nets", "Nets", '"Brooklyn Nets"'),
    "cha": ("Charlotte Hornets", "Hornets", '"Charlotte Hornets"'),
    "chi": ("Chicago Bulls", "Bulls", '"Chicago Bulls"'),
    "cle": ("Cleveland Cavaliers", "Cavaliers", "Cavaliers"),
    "dal": ("Dallas Mavericks", "Mavericks", "Mavericks"),
    "den": ("Denver Nuggets", "Nuggets", "Nuggets"),
    "det": ("Detroit Pistons", "Pistons", '"Detroit Pistons"'),
    "gsw": ("Golden State Warriors", "Warriors", '"Golden State Warriors"'),
    "hou": ("Houston Rockets", "Rockets", '"Houston Rockets"'),
    "ind": ("Indiana Pacers", "Pacers", '"Indiana Pacers"'),
    "lac": ("Los Angeles Clippers", "Clippers", "Clippers"),
    "lal": ("Los Angeles Lakers", "Lakers", "Lakers"),
    "mem": ("Memphis Grizzlies", "Grizzlies", "Grizzlies"),
    "mia": ("Miami Heat", "Heat", '"Miami Heat"'),
    "mil": ("Milwaukee Bucks", "Bucks", '"Milwaukee Bucks"'),
    "min": ("Minnesota Timberwolves", "Timberwolves", "Timberwolves"),
    "nop": ("New Orleans Pelicans", "Pelicans", '"New Orleans Pelicans"'),
    "nyk": ("New York Knicks", "Knicks", "Knicks"),
    "okc": ("Oklahoma City Thunder", "Thunder", '"OKC Thunder"'),
    "orl": ("Orlando Magic", "Magic", '"Orlando Magic"'),
    "phi": ("Philadelphia 76ers", "76ers", "76ers"),
    "phx": ("Phoenix Suns", "Suns", '"Phoenix Suns"'),
    "por": ("Portland Trail Blazers", "Trail Blazers", '"Trail Blazers"'),
    "sac": ("Sacramento Kings", "Kings", '"Sacramento Kings"'),
    "sas": ("San Antonio Spurs", "Spurs", '"San Antonio Spurs"'),
    "tor": ("Toronto Raptors", "Raptors", "Raptors"),
    "uta": ("Utah Jazz", "Jazz", '"Utah Jazz"'),
    "was": ("Washington Wizards", "Wizards", '"Washington Wizards"'),
}
