"""Stockfish analysis of the first N plies of every game + error detection.

Evaluations are cached in SQLite by (FEN, engine tag) in table `evals_v2`; the tag holds the engine
version and search settings, so changing either never mixes old and new evals. Every error of the user
in the analysed plies goes to `errors` (one row per error); per-game metadata goes to `game_results`.
"""
import json
import math
import multiprocessing as mp
import sqlite3
import sys
import time

import chess
import chess.engine
import pandas as pd

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS evals_v2(
  fen TEXT NOT NULL, engine TEXT NOT NULL, cp INTEGER NOT NULL, best TEXT, depth INTEGER, PRIMARY KEY(fen, engine));
CREATE TABLE IF NOT EXISTS explorer(fen TEXT, params TEXT, json TEXT, PRIMARY KEY(fen, params));
"""


def win_pct(cp: float) -> float:
    """Winning chances (0-100) for the side whose POV `cp` is in; the formula Lichess uses for accuracy."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def db():
    con = sqlite3.connect(C.DB_FILE, timeout=60)
    con.executescript(SCHEMA)
    return con


def fen_key(board: chess.Board) -> str:
    """FEN without move counters (transposition-friendly cache key)."""
    return " ".join(board.fen().split()[:4])


# ---------------- game parsing ----------------

def load_games():
    with open(C.GAMES_FILE, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def classify(g):
    """Return (color, skip_reason). color is 'white'/'black'."""
    if g.get("variant") != "standard" or "initialFen" in g:
        return None, "non-standard start position/variant"
    me = C.USER.lower()
    w = (g["players"]["white"].get("user") or {}).get("id")
    b = (g["players"]["black"].get("user") or {}).get("id")
    color = "white" if w == me else "black" if b == me else None
    if color is None:
        return None, "user not found in game"
    if not g.get("moves"):
        return None, "no moves"
    return color, None


# ---------------- engine ----------------

_engine = None
_tag = None


def _init_worker():
    global _engine, _tag
    _engine = chess.engine.SimpleEngine.popen_uci(C.STOCKFISH)
    _engine.configure({"Threads": 1, "Hash": C.ENGINE_HASH})
    _tag = f"{_engine.id.get('name', '?')}|depth={C.ENGINE_DEPTH}|threads=1|hash={C.ENGINE_HASH}"


def _eval(board, con, new):
    """White-POV centipawns (mate -> +-10000) and best move uci, cached by (FEN, engine tag)."""
    if board.is_checkmate():
        return (-10000 if board.turn == chess.WHITE else 10000), None
    if board.is_stalemate() or board.is_insufficient_material():
        return 0, None
    key = fen_key(board)
    if key in new:
        return new[key][0], new[key][1]
    row = con.execute("SELECT cp,best FROM evals_v2 WHERE fen=? AND engine=?", (key, _tag)).fetchone()
    if row:
        return row[0], row[1]
    info = _engine.analyse(board, chess.engine.Limit(depth=C.ENGINE_DEPTH))
    cp = info["score"].white().score(mate_score=10000)
    best = info["pv"][0].uci() if info.get("pv") else None
    new[key] = (cp, best, info.get("depth", 0))
    return cp, best


def analyze_game(g):
    """All errors of the user in the first ANALYZE_PLIES plies (analysis does not stop at the first one,
    so an intentional gambit move does not hide the real mistakes that follow it)."""
    color, _ = classify(g)
    me_white = color == "white"
    con = sqlite3.connect(C.DB_FILE, timeout=60)
    new, errors = {}, []
    board = chess.Board()
    sans = g["moves"].split()[: C.ANALYZE_PLIES]
    res = dict(id=g["id"], color=color, plies_analyzed=0)
    try:
        for i, san in enumerate(sans):
            mine = (board.turn == chess.WHITE) == me_white
            before_cp, best = _eval(board, con, new) if mine else (None, None)
            fen_before = board.fen()
            try:
                move = board.parse_san(san)
            except ValueError:
                break
            board.push(move)
            res["plies_analyzed"] = i + 1
            if not mine:
                continue
            after_cp, _ = _eval(board, con, new)
            sgn = 1 if me_white else -1
            b, a = sgn * before_cp, sgn * after_cp
            wb, wa = win_pct(b), win_pct(a)
            if wb - wa >= C.ERROR_WIN_DROP:
                errors.append(dict(id=g["id"], ply=i + 1, fen_before=fen_before, played=move.uci(), played_san=san,
                                   best=best, eval_before=b, eval_after=a, win_before=wb, win_after=wa, drop=wb - wa))
    finally:
        con.close()
    return res, errors, new, _tag


def run(limit=None):
    games = load_games()
    todo, skipped = [], []
    for g in games:
        color, why = classify(g)
        (todo if color else skipped).append(g if color else (g["id"], why))
    if limit:
        todo = todo[:limit]
    con = db()
    results, all_errors, t0 = [], [], time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(C.WORKERS, initializer=_init_worker) as pool:
        for k, (res, errs, new, tag) in enumerate(pool.imap_unordered(analyze_game, todo, chunksize=2), 1):
            results.append(res)
            all_errors.extend(errs)
            if new:
                con.executemany("INSERT OR REPLACE INTO evals_v2 VALUES(?,?,?,?,?)",
                                [(f, tag, v[0], v[1], v[2]) for f, v in new.items()])
                con.commit()
            if k % 25 == 0:
                print(f"  {k}/{len(todo)} games, {time.time()-t0:.0f}s", flush=True)
    meta = {g["id"]: g for g in games}
    rows = []
    for r in results:
        g = meta[r["id"]]
        col = r["color"]
        me, opp = g["players"][col], g["players"]["black" if col == "white" else "white"]
        w = g.get("winner")
        score = 0.5 if w is None else 1.0 if w == col else 0.0
        seq = g["moves"].split()[: C.LINE_MAX_PLIES]
        speed = "bullet" if g["speed"] == "ultraBullet" else g["speed"]
        rows.append({**r, "speed": speed, "score": score,
                     "result": "win" if score == 1 else "draw" if score == .5 else "loss",
                     "line": " ".join(seq), "eco": (g.get("opening") or {}).get("eco", "?"),
                     "opening": (g.get("opening") or {}).get("name", "?"),
                     "rating": me.get("rating"), "opp_rating": opp.get("rating"),
                     "created": g["createdAt"], "moves": g["moves"]})
    df = pd.DataFrame(rows)
    df.to_sql("game_results", con, if_exists="replace", index=False)
    pd.DataFrame(all_errors, columns=["id", "ply", "fen_before", "played", "played_san", "best", "eval_before",
                                      "eval_after", "win_before", "win_after", "drop"]
                 ).to_sql("errors", con, if_exists="replace", index=False)
    pd.DataFrame(skipped, columns=["id", "reason"]).to_sql("skipped", con, if_exists="replace", index=False)
    con.commit()
    print(f"Analyzed {len(df)} games, skipped {len(skipped)}; {len(all_errors)} errors; "
          f"{con.execute('select count(*) from evals_v2').fetchone()[0]} cached evals; {time.time()-t0:.0f}s")
    return df


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else None)
