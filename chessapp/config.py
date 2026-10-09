"""Shared configuration and thresholds (documented in README)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

USER = "yairklo"
MAX_GAMES = 1000
GAMES_FILE = DATA / "games.ndjson"          # default player (kept where it always was)
(DATA / "games").mkdir(exist_ok=True)


def games_file(user: str = USER) -> Path:
    """Downloaded games of a player: the default player's file, or data/games/<user>.ndjson."""
    return GAMES_FILE if user.lower() == USER.lower() else DATA / "games" / f"{user.lower()}.ndjson"


DB_FILE = DATA / "cache.sqlite"

_exe = ROOT / "engine" / "stockfish" / "stockfish-windows-x86-64-universal.exe"
STOCKFISH = os.environ.get("STOCKFISH_PATH") or (str(_exe) if _exe.exists() else "stockfish")

# --- engine analysis ---
ANALYZE_PLIES = 20          # first N half-moves of every game
ENGINE_DEPTH = 16           # fixed depth, no time limit (stable evals; part of the cache key)
ENGINE_HASH = 64
WORKERS = max(1, min(8, (os.cpu_count() or 4) // 2))

# --- errors ---
# An error is a drop of >= ERROR_WIN_DROP points in the mover's winning chances (Lichess win% formula),
# so +5 -> +4 (still winning) is not an error but +0.5 -> -0.7 is.
ERROR_WIN_DROP = 12            # default; adjustable in the dashboard sidebar
ERROR_WIN_DROP_CHOICES = [8, 10, 12, 15, 20]
ERROR_STORE_MIN = 6            # drops >= this are stored, so the threshold can change without re-running the engine
PV_PLIES = 6                   # length of the engine lines shown on mistake cards

# --- statistics ---
MIN_GROUP_GAMES = 10        # groups smaller than this are never shown
LINE_MAX_PLIES = 12         # deepest line used when grouping openings
EARLY_ERROR_MOVE = 8        # "early" = first error on own move <= 8
EARLY_ERROR_SHARE = 0.30    # "recurring" = >=30% of group's games have an early first error

# confidence that an opening really differs from the player's other games in that colour (two-proportion z)
CONF_HIGH_Z, CONF_HIGH_GAMES = 2.5, 20
CONF_MID_Z, CONF_MID_GAMES = 2.0, 15

TOXIC_MARGIN = 0.05         # toxic also needs score >= 5 points below the same colour's average ...
                            # ... and the same exact error (position + move) in >= MIN_PROBLEM_GAMES games

# --- recommendations ---
GAMBIT_MIN_GAMES = 5        # a played move with >= 5 games and above-average score is a working choice, not a problem
TOP_POSITIONS = 5
MIN_PROBLEM_GAMES = 3       # a "recurring" mistake = same move in the same position in >= 3 games
TOKEN_FILE = DATA / "lichess_token.txt"   # data/ is git-ignored, so the token never reaches the repository


def lichess_token():
    """Personal Lichess token: the LICHESS_TOKEN environment variable, else data/lichess_token.txt.
    Read on every call, so saving the file takes effect without restarting the dashboard."""
    tok = os.environ.get("LICHESS_TOKEN")
    if not tok and TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
        tok = tok.split("=", 1)[1] if tok.upper().startswith("LICHESS_TOKEN=") else tok  # also accept KEY=value
        tok = tok.strip().strip('"').strip("'")
    return tok or None
EXPLORER_URL = "https://explorer.lichess.ovh/lichess"

# --- learning over time ---
LEARN_MIN_REACHED = 3       # fewer visits to the position than this -> "not enough data"
LEARN_FIXED_AFTER = 3       # mistake counts as learned after >= 3 later visits without repeating it
LEARN_RECENT = 5            # "recent rate" = share of mistakes in the last 5 visits

# --- dashboard ---
TREND_DAYS = 30             # "recent" period compared with everything before it
