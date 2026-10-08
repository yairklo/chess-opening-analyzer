"""Download the user's last games from Lichess (NDJSON). Use --refresh to re-download."""
import argparse
import sys
import time

import requests

from .config import GAMES_FILE, LICHESS_TOKEN, MAX_GAMES, USER


def fetch(refresh: bool = False) -> int:
    if GAMES_FILE.exists() and not refresh:
        n = sum(1 for _ in open(GAMES_FILE, encoding="utf-8"))
        print(f"{GAMES_FILE} exists ({n} games); skipping download (use --refresh).")
        return n
    headers = {"Accept": "application/x-ndjson", "User-Agent": "yairklo-opening-analyzer"}
    if LICHESS_TOKEN:
        headers["Authorization"] = f"Bearer {LICHESS_TOKEN}"
    params = dict(max=MAX_GAMES, opening="true", evals="true", clocks="false")
    url = f"https://lichess.org/api/games/user/{USER}"
    while True:
        r = requests.get(url, params=params, headers=headers, stream=True, timeout=120)
        if r.status_code == 429:
            print("429 from Lichess; waiting 60s...", file=sys.stderr)
            time.sleep(60)
            continue
        r.raise_for_status()
        break
    tmp = GAMES_FILE.with_suffix(".tmp")
    n = 0
    with open(tmp, "wb") as f:
        for line in r.iter_lines():
            if line:
                f.write(line + b"\n")
                n += 1
    tmp.replace(GAMES_FILE)
    print(f"Downloaded {n} games to {GAMES_FILE}")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    fetch(ap.parse_args().refresh)
