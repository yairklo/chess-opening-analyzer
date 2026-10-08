"""Stockfish analysis of the first N plies of every game + first-error detection.

Evaluations are cached in SQLite by FEN (table `evals`). Per-game results go to
`game_results`; the positions of first errors to `errors`.
"""
import json
import multiprocessing as mp
import sqlite3
import sys
import time

import chess
import chess.engine
import pandas as pd

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS evals(
  fen TEXT PRIMARY KEY, cp INTEGER NOT NULL, best TEXT, depth INTEGER);
CREATE TABLE IF NOT EXISTS explorer(fen TEXT, params TEXT, json TEXT, PRIMARY KEY(fen, params));
"""


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


def _init_worker():
    global _engine
    _engine = chess.engine.SimpleEngine.popen_uci(C.STOCKFISH)
    _engine.configure({"Threads": 1, "Hash": 64})


def _eval(board, con, new):
    """White-POV centipawns (mate -> +-10000) and best move uci, cached by FEN."""
    if board.is_checkmate():
        return (-10000 if board.turn == chess.WHITE else 10000), None
    if board.is_stalemate() or board.is_insufficient_material():
        return 0, None
    key = fen_key(board)
    if key in new:
        return new[key][0], new[key][1]
    row = con.execute("SELECT cp,best FROM evals WHERE fen=?", (key,)).fetchone()
    if row:
        return row[0], row[1]
    info = _engine.analyse(board, chess.engine.Limit(depth=C.ENGINE_DEPTH, time=C.ENGINE_TIME))
    cp = info["score"].white().score(mate_score=10000)
    best = info["pv"][0].uci() if info.get("pv") else None
    new[key] = (cp, best, info.get("depth", 0))
    return cp, best


def _clamp(x):
    return max(-C.EVAL_CLAMP, min(C.EVAL_CLAMP, x))


def analyze_game(g):
    color, _ = classify(g)
    me_white = color == "white"
    con = sqlite3.connect(C.DB_FILE, timeout=60)
    new = {}
    board = chess.Board()
    sans = g["moves"].split()[: C.ANALYZE_PLIES]
    res = dict(id=g["id"], color=color, first_error_ply=None, plies_analyzed=0)
    try:
        for i, san in enumerate(sans):
            mover_white = board.turn == chess.WHITE
            before_cp, best = _eval(board, con, new) if mover_white == me_white else (None, None)
            fen_before = board.fen()
            try:
                move = board.parse_san(san)
            except ValueError:
                break
            board.push(move)
            res["plies_analyzed"] = i + 1
            if mover_white != me_white:
                continue
            after_cp, _ = _eval(board, con, new)
            sgn = 1 if me_white else -1
            b, a = sgn * before_cp, sgn * after_cp
            drop = _clamp(b) - _clamp(a)
            crossed = b > C.LOSING_CP and a <= C.LOSING_CP
            if drop >= C.ERROR_DROP_CP or crossed:
                res.update(first_error_ply=i + 1, fen_before=fen_before, played=move.uci(),
                           played_san=san, best=best, eval_before=b, eval_after=a,
                           drop=drop, kind="crossed-to-losing" if crossed and drop < C.ERROR_DROP_CP else "drop")
                break
    finally:
        con.close()
    return res, new


def run(limit=None):
    games = load_games()
    todo, skipped = [], []
    for g in games:
        color, why = classify(g)
        (todo if color else skipped).append(g if color else (g["id"], why))
    if limit:
        todo = todo[:limit]
    con = db()
    results, t0 = [], time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(C.WORKERS, initializer=_init_worker) as pool:
        for k, (res, new) in enumerate(pool.imap_unordered(analyze_game, todo, chunksize=2), 1):
            results.append(res)
            if new:
                con.executemany("INSERT OR REPLACE INTO evals VALUES(?,?,?,?)",
                                [(f, v[0], v[1], v[2]) for f, v in new.items()])
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
    pd.DataFrame(skipped, columns=["id", "reason"]).to_sql("skipped", con, if_exists="replace", index=False)
    con.commit()
    print(f"Analyzed {len(df)} games, skipped {len(skipped)}; "
          f"{con.execute('select count(*) from evals').fetchone()[0]} cached evals; {time.time()-t0:.0f}s")
    return df


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else None)
