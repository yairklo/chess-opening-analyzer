"""Download a player's last games from Lichess (NDJSON). Use --refresh to re-download."""
import argparse
import re
import sys
import time

import requests

from . import config as C

USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,29}$")


class FetchError(Exception):
    pass


def fetch(user: str = C.USER, refresh: bool = False, max_games: int = C.MAX_GAMES, on_progress=None) -> int:
    """Download up to `max_games` of the player's games; `on_progress(n)` is called while streaming."""
    if not USERNAME.match(user):
        raise FetchError(f"'{user}' is not a valid Lichess username")
    out = C.games_file(user)
    if out.exists() and not refresh:
        n = sum(1 for _ in open(out, encoding="utf-8"))
        print(f"{out} exists ({n} games); skipping download (use --refresh).")
        return n
    headers = {"Accept": "application/x-ndjson", "User-Agent": "yairklo-opening-analyzer"}
    if C.LICHESS_TOKEN:
        headers["Authorization"] = f"Bearer {C.LICHESS_TOKEN}"
    params = dict(max=max_games, opening="true", evals="false", clocks="false")
    url = f"https://lichess.org/api/games/user/{user}"
    while True:
        r = requests.get(url, params=params, headers=headers, stream=True, timeout=120)
        if r.status_code == 429:
            print("429 from Lichess; waiting 60s...", file=sys.stderr)
            time.sleep(60)
            continue
        if r.status_code == 404:
            raise FetchError(f"Lichess user '{user}' not found")
        r.raise_for_status()
        break
    tmp = out.with_suffix(".tmp")
    n = 0
    with open(tmp, "wb") as f:
        for line in r.iter_lines():
            if line:
                f.write(line + b"\n")
                n += 1
                if on_progress and n % 20 == 0:
                    on_progress(n)
    if n == 0:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"no games found for '{user}'")
    tmp.replace(out)
    print(f"Downloaded {n} games to {out}")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("user", nargs="?", default=C.USER)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--max", type=int, default=C.MAX_GAMES)
    a = ap.parse_args()
    fetch(a.user, a.refresh, a.max)
