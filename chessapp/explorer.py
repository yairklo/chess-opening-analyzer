"""Lichess Opening Explorer lookups (cached in SQLite, only for the problem positions).

Since 2025 the explorer requires an OAuth token: set LICHESS_TOKEN (no scopes needed).
Without a token every lookup returns None and the dashboard shows a note instead.
"""
import json

import requests

from . import config as C
from .analyze import db

RATING_BUCKETS = [1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]


def similar_ratings(rating: int):
    """Explorer buckets are [b, next_b): use the user's bucket and the one above."""
    i = max([k for k, b in enumerate(RATING_BUCKETS) if b <= rating], default=0)
    return ",".join(str(b) for b in RATING_BUCKETS[i:i + 2])


def lookup(fen: str, rating: int, speeds: str = "blitz,rapid"):
    if not C.LICHESS_TOKEN:
        return None
    ratings = similar_ratings(rating)
    params = f"{ratings}|{speeds}"
    con = db()
    row = con.execute("SELECT json FROM explorer WHERE fen=? AND params=?", (fen, params)).fetchone()
    if row:
        return json.loads(row[0])
    r = requests.get(C.EXPLORER_URL, params={"fen": fen, "ratings": ratings, "speeds": speeds, "moves": 6},
                     headers={"Authorization": f"Bearer {C.LICHESS_TOKEN}", "User-Agent": "yairklo-opening-analyzer"},
                     timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    con.execute("INSERT OR REPLACE INTO explorer VALUES(?,?,?)", (fen, params, json.dumps(data)))
    con.commit()
    return data
