"""Line trainer: drills a line from a mistake onward, and decides how deep the line is worth drilling.

At every position where the trainee is to move we look at three signals:
  * critical - the engine's best move beats the second best by >= TRAIN_CRIT_GAP win% points, so a plausible
               alternative loses (an "only move" moment: often the 4th-7th move, not the first);
  * known    - the position is still reached in >= TRAIN_LEVEL_GAMES Lichess games at the player's level, or in
               >= TRAIN_MASTERS_GAMES master games (established theory);
  * default  - the first TRAIN_DEFAULT_MOVES own moves are always drilled (used when nothing is known).
The line stops after TRAIN_QUIET_STOP own moves in a row with neither signal, or at TRAIN_MAX_MOVES.
Only the branch the trainee actually walks is computed; engine results are cached in SQLite (`multipv_v1`).
"""
import json
import random

import chess
import chess.engine

from . import config as C
from .analyze import db, engine_tag, fen_key, win_pct
from .explorer import explore, explore_masters, games_in
from .lines import _get_engine, _lock, pv

SCHEMA = """CREATE TABLE IF NOT EXISTS multipv_v1(
  fen TEXT NOT NULL, engine TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(fen, engine))"""


def top_moves(board: chess.Board, n: int = 3):
    """The engine's n best moves, best first: [(uci, white-POV centipawns)]."""
    if board.is_game_over():
        return []
    con = db()
    con.execute(SCHEMA)
    with _lock:
        eng = _get_engine()
        tag = engine_tag(eng) + f"|multipv{n}"
        row = con.execute("SELECT data FROM multipv_v1 WHERE fen=? AND engine=?", (fen_key(board), tag)).fetchone()
        if row:
            return [tuple(x) for x in json.loads(row[0])]
        infos = eng.analyse(board, chess.engine.Limit(depth=C.ENGINE_DEPTH), multipv=n)
    out = [(i["pv"][0].uci(), i["score"].white().score(mate_score=10000)) for i in infos if i.get("pv")]
    con.execute("INSERT OR REPLACE INTO multipv_v1 VALUES(?,?,?)", (fen_key(board), tag, json.dumps(out)))
    con.commit()
    return out


def pov(cp, color):
    return cp if color == "white" else -cp


def node(board: chess.Board, color: str, rating: int) -> dict:
    """Everything the trainer needs about a position where the trainee (`color`) is to move."""
    mpv = top_moves(board, 3)
    wins = [win_pct(pov(cp, color)) for _, cp in mpv]
    gap = wins[0] - wins[1] if len(wins) > 1 else 0.0
    level, level_err = explore(board.fen(), rating)
    masters, _ = explore_masters(board.fen())
    level_n, masters_n = games_in(level), games_in(masters)
    return dict(mpv=mpv, wins=wins, gap=gap,
                critical=board.legal_moves.count() > 1 and gap >= C.TRAIN_CRIT_GAP,
                level=level, masters=masters, level_n=level_n, masters_n=masters_n, level_err=level_err,
                known=level_n >= C.TRAIN_LEVEL_GAMES or masters_n >= C.TRAIN_MASTERS_GAMES)


def decide(done: int, quiet: int, info: dict, board: chess.Board):
    """Whether to ask another own move. Returns (go_on, quiet_count, reason)."""
    if board.is_game_over():
        return False, quiet, "over"
    if done >= C.TRAIN_MAX_MOVES:
        return False, quiet, "max"
    reason = "critical" if info["critical"] else "known" if info["known"] else None
    if reason:
        return True, 0, reason
    if done < C.TRAIN_DEFAULT_MOVES:
        return True, quiet, "default"
    quiet += 1
    return quiet < C.TRAIN_QUIET_STOP, quiet, "quiet"


def evaluate(board: chess.Board, info: dict, uci: str, color: str) -> dict:
    """How good the trainee's choice is, relative to the engine's best move (in win% points)."""
    scores = dict(info["mpv"])
    if uci in scores:
        cp = scores[uci]
    else:
        after = board.copy()
        after.push(chess.Move.from_uci(uci))
        cp = pv(after)[1]
    win = win_pct(pov(cp, color))
    drop = max(0.0, info["wins"][0] - win)
    best = info["mpv"][0][0]
    return dict(uci=uci, best=best, drop=drop, win=win, ok=drop <= C.TRAIN_ACCEPT, is_best=uci == best)


def my_options(board: chess.Board, info: dict, mistake_uci: str = None, k: int = 4) -> list:
    """Moves to choose from: the engine's best, the trainee's old mistake (if any), moves that are popular at
    the player's level (often the tempting wrong ones), the engine's alternatives, then random legal moves."""
    out = []

    def add(u):
        if u and u not in out and chess.Move.from_uci(u) in board.legal_moves:
            out.append(u)

    add(info["mpv"][0][0] if info["mpv"] else None)
    add(mistake_uci)
    for m in sorted((info["level"] or {}).get("moves", []), key=lambda m: -(m["white"] + m["draws"] + m["black"])):
        add(m["uci"])
    for u, _ in info["mpv"][1:]:
        add(u)
    rng = random.Random(fen_key(board))
    rest = [m.uci() for m in board.legal_moves if m.uci() not in out]
    rng.shuffle(rest)
    out = (out + rest)[:k]
    rng.shuffle(out)
    return out


def opponent_options(board: chess.Board, rating: int, from_games=None, k: int = 4) -> list:
    """Replies to choose for the opponent, each with why it is offered: popular at the player's level,
    the engine's strongest, played against the trainee in real games, or the masters' main move."""
    opts = {}

    def add(uci, tag, order):
        m = chess.Move.from_uci(uci)
        if m not in board.legal_moves:
            return
        o = opts.setdefault(uci, {"uci": uci, "san": board.san(m), "tags": [], "order": order})
        o["order"] = min(o["order"], order)
        if tag not in o["tags"]:
            o["tags"].append(tag)

    level, _ = explore(board.fen(), rating)
    masters, _ = explore_masters(board.fen())
    total = games_in(level)
    for i, m in enumerate(sorted((level or {}).get("moves", []), key=lambda m: -(m["white"] + m["draws"] + m["black"]))[:3]):
        n = m["white"] + m["draws"] + m["black"]
        add(m["uci"], f"נפוצה ברמה שלך · {n / total:.0%}" if total else "נפוצה ברמה שלך", i)
    mpv = top_moves(board, 3)
    if mpv:
        add(mpv[0][0], "החזקה ביותר לפי המנוע", 0.5)
    for r in from_games or []:
        try:
            add(board.parse_san(r["san"]).uci(), f"שוחקה נגדך · {r['n']} משחקים", 1.5)
        except ValueError:
            pass
    if masters and masters.get("moves"):
        add(masters["moves"][0]["uci"], "הנפוצה אצל מאסטרים", 2.5)
    for u, _ in mpv[1:]:
        if len(opts) >= 3:
            break
        add(u, "חלופה של המנוע", 3)
    return sorted(opts.values(), key=lambda o: o["order"])[:k]
