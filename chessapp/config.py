"""Shared configuration and thresholds (documented in README)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

USER = "yairklo"
MAX_GAMES = 1000
GAMES_FILE = DATA / "games.ndjson"
DB_FILE = DATA / "cache.sqlite"

_exe = ROOT / "engine" / "stockfish" / "stockfish-windows-x86-64-universal.exe"
STOCKFISH = os.environ.get("STOCKFISH_PATH") or (str(_exe) if _exe.exists() else "stockfish")

# --- engine analysis ---
ANALYZE_PLIES = 20          # first N half-moves of every game
ENGINE_DEPTH = 16           # stop at depth 16 ...
ENGINE_TIME = 0.3           # ... or 0.3s per position, whichever comes first
WORKERS = max(1, min(8, (os.cpu_count() or 4) // 2))

# --- first error ---
ERROR_DROP_CP = 100         # eval drop (mover POV) that counts as an error
LOSING_CP = -200            # <= this is "losing"; crossing from above it to it is an error
EVAL_CLAMP = 1000           # evals are clamped to +-1000cp before measuring drops

# --- statistics ---
MIN_GROUP_GAMES = 10        # groups smaller than this are never shown
LINE_MAX_PLIES = 12         # deepest line used when grouping openings
EARLY_ERROR_MOVE = 8        # "early" = first error on own move <= 8
EARLY_ERROR_SHARE = 0.30    # "recurring" = >=30% of group's games have an early first error

TOXIC_MARGIN = 0.05         # toxic also needs score >= 5 points below the overall score

# --- recommendations ---
GAMBIT_MIN_GAMES = 5        # a played move with >= 5 games and above-average score is a working choice, not a problem
TOP_POSITIONS = 5
LICHESS_TOKEN = os.environ.get("LICHESS_TOKEN")
EXPLORER_URL = "https://explorer.lichess.ovh/lichess"

# --- learning over time ---
LEARN_MIN_REACHED = 3       # fewer visits to the position than this -> "not enough data"
LEARN_FIXED_AFTER = 3       # mistake counts as learned after >= 3 later visits without repeating it
LEARN_RECENT = 5            # "recent rate" = share of mistakes in the last 5 visits
