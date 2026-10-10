"""Lichess Opening Explorer lookups (cached in SQLite, only for the problem positions).

The explorer API currently requires an OAuth token: put a personal token (no scopes needed) in data/lichess_token.txt or the LICHESS_TOKEN environment variable.
Without a token, or when the request fails, `explore` returns (None, reason) and the dashboard says why.
"""
import json

import requests

from . import config as C
from .analyze import db

RATING_BUCKETS = [1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]
REASONS = {401: "הטוקן לא תקף (401)", 403: "אין הרשאה (403)", 429: "יותר מדי בקשות ל‑Lichess, נסו שוב בעוד דקה (429)"}


def similar_ratings(rating: int):
    """Explorer buckets are [b, next_b): use the user's bucket and the one above."""
    i = max([k for k, b in enumerate(RATING_BUCKETS) if b <= rating], default=0)
    return ",".join(str(b) for b in RATING_BUCKETS[i:i + 2])


def _fetch(url: str, params: dict, cache_params: str, fen: str):
    """(data, None) or (None, reason in Hebrew). Successful answers are cached by (fen, cache_params); failures are not."""
    if not C.lichess_token():
        return None, "לא הוגדר טוקן של Lichess"
    con = db()
    row = con.execute("SELECT json FROM explorer WHERE fen=? AND params=?", (fen, cache_params)).fetchone()
    if row:
        return json.loads(row[0]), None
    try:
        r = requests.get(url, params=params, timeout=15,
                         headers={"Authorization": f"Bearer {C.lichess_token()}", "User-Agent": "yairklo-opening-analyzer"})
    except requests.RequestException as e:
        return None, f"אין חיבור ל‑Lichess ({type(e).__name__})"
    if r.status_code != 200:
        return None, REASONS.get(r.status_code, f"Lichess החזיר שגיאה {r.status_code}")
    try:
        data = r.json()
        data["moves"]  # noqa: B018 - make sure the answer has the expected shape
    except (ValueError, KeyError, TypeError):
        return None, "תשובה לא צפויה מ‑Lichess"
    con.execute("INSERT OR REPLACE INTO explorer VALUES(?,?,?)", (fen, cache_params, json.dumps(data)))
    con.commit()
    return data, None


def explore(fen: str, rating: int, speeds: str = "blitz,rapid"):
    """Lichess games of players rated like `rating` in this position."""
    ratings = similar_ratings(rating)
    return _fetch(C.EXPLORER_URL, {"fen": fen, "ratings": ratings, "speeds": speeds, "moves": 6},
                  f"{ratings}|{speeds}", fen)


def explore_masters(fen: str):
    """Over-the-board master games in this position: how far established theory goes."""
    return _fetch(C.MASTERS_URL, {"fen": fen, "moves": 6, "topGames": 0}, "masters", fen)


def games_in(data) -> int:
    return data["white"] + data["draws"] + data["black"] if data else 0


def lookup(fen: str, rating: int, speeds: str = "blitz,rapid"):
    """Explorer data or None (kept for callers that do not need the reason)."""
    return explore(fen, rating, speeds)[0]
