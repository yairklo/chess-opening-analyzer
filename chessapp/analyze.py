"""Stockfish analysis of the first N plies of every game + error detection.

Evaluations are cached in SQLite by (FEN, engine tag) in table `evals_v2`; the tag holds the engine
version and search settings, so changing either never mixes old and new evals. Every error of the player
in the analysed plies goes to `errors` (one row per error); per-game metadata goes to `game_results`.
All per-game tables carry a `user` column, so several players can be analysed side by side.

    python -m chessapp.analyze [user] [--quick] [--limit N]

--quick only builds `game_results` (results + opening lines, no engine): enough for the opening tree.
"""
import argparse
import json
import math
import multiprocessing as mp
import sqlite3
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
    # migrate single-player tables (from before multi-player support): their rows belong to the default user
    for t in ("game_results", "errors", "skipped"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        if cols and "user" not in cols:
            con.execute(f"ALTER TABLE {t} ADD COLUMN user TEXT NOT NULL DEFAULT '{C.USER.lower()}'")
            con.commit()
    return con


def users():
    """Players that have results in the database, default player first."""
    con = db()
    try:
        found = [r[0] for r in con.execute("SELECT DISTINCT user FROM game_results")]
    except sqlite3.OperationalError:
        found = []
    me = C.USER.lower()
    return ([me] if me in found else []) + sorted(u for u in found if u != me)


def fen_key(board: chess.Board) -> str:
    """FEN without move counters (transposition-friendly cache key)."""
    return " ".join(board.fen().split()[:4])


# ---------------- game parsing ----------------

def load_games(user=C.USER):
    with open(C.games_file(user), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def classify(g, user=C.USER):
    """Return (color, skip_reason). color is 'white'/'black'."""
    if g.get("variant") != "standard" or "initialFen" in g:
        return None, "non-standard start position/variant"
    me = user.lower()
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


def analyze_game(job):
    """All errors of the player in the first ANALYZE_PLIES plies (analysis does not stop at the first one,
    so an intentional gambit move does not hide the real mistakes that follow it)."""
    g, user = job
    color, _ = classify(g, user)
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


def _split(games, user):
    todo, skipped = [], []
    for g in games:
        color, why = classify(g, user)
        (todo if color else skipped).append(g if color else (g["id"], why))
    return todo, skipped


def build_results(user=C.USER):
    """Per-game rows (result, opening line, rating...) from the downloaded games; no engine needed."""
    user = user.lower()
    games = load_games(user)
    todo, skipped = _split(games, user)
    rows = []
    for g in todo:
        col = "white" if (g["players"]["white"].get("user") or {}).get("id") == user else "black"
        me, opp = g["players"][col], g["players"]["black" if col == "white" else "white"]
        w = g.get("winner")
        score = 0.5 if w is None else 1.0 if w == col else 0.0
        rows.append({"id": g["id"], "color": col, "plies_analyzed": min(len(g["moves"].split()), C.ANALYZE_PLIES),
                     "speed": "bullet" if g["speed"] == "ultraBullet" else g["speed"], "score": score,
                     "result": "win" if score == 1 else "draw" if score == .5 else "loss",
                     "line": " ".join(g["moves"].split()[: C.LINE_MAX_PLIES]),
                     "eco": (g.get("opening") or {}).get("eco", "?"), "opening": (g.get("opening") or {}).get("name", "?"),
                     "rating": me.get("rating"), "opp_rating": opp.get("rating"),
                     "created": g["createdAt"], "moves": g["moves"], "user": user})
    df = pd.DataFrame(rows)
    con = db()
    _replace(con, "game_results", df, user)
    _replace(con, "skipped", pd.DataFrame([(i, why, user) for i, why in skipped], columns=["id", "reason", "user"]), user)
    con.commit()
    print(f"{user}: {len(df)} games, skipped {len(skipped)}", flush=True)
    return df


def _replace(con, table, df, user):
    """Replace one player's rows in a table (creating the table from `df` if needed)."""
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if exists:
        con.execute(f"DELETE FROM {table} WHERE user=?", (user,))
    df.to_sql(table, con, if_exists="append", index=False)


ERROR_COLUMNS = ["id", "ply", "fen_before", "played", "played_san", "best", "eval_before",
                 "eval_after", "win_before", "win_after", "drop"]


def run(user=C.USER, limit=None):
    """Results + Stockfish errors for one player. Prints `PROGRESS k/n` lines (read by the dashboard)."""
    user = user.lower()
    build_results(user)
    todo, _ = _split(load_games(user), user)
    if limit:
        todo = todo[:limit]
    con = db()
    all_errors, t0 = [], time.time()
    print(f"PROGRESS 0/{len(todo)}", flush=True)
    ctx = mp.get_context("spawn")
    with ctx.Pool(C.WORKERS, initializer=_init_worker) as pool:
        jobs = ((g, user) for g in todo)
        for k, (res, errs, new, tag) in enumerate(pool.imap_unordered(analyze_game, jobs, chunksize=2), 1):
            all_errors.extend(errs)
            if new:
                con.executemany("INSERT OR REPLACE INTO evals_v2 VALUES(?,?,?,?,?)",
                                [(f, tag, v[0], v[1], v[2]) for f, v in new.items()])
                con.commit()
            if k % 10 == 0 or k == len(todo):
                print(f"PROGRESS {k}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    errors = pd.DataFrame(all_errors, columns=ERROR_COLUMNS).assign(user=user)
    _replace(con, "errors", errors, user)
    con.commit()
    print(f"DONE {user}: {len(todo)} games, {len(errors)} errors; "
          f"{con.execute('select count(*) from evals_v2').fetchone()[0]} cached evals; {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("user", nargs="?", default=C.USER)
    ap.add_argument("--quick", action="store_true", help="results only, no engine")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    build_results(a.user) if a.quick else run(a.user, a.limit)
