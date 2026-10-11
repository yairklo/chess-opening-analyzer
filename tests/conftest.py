"""Test data: a throw-away data directory with a few synthetic players, set up before `chessapp` is imported.

Players (all non-default, so the dashboard speaks in the third person and never starts the engine or trainer):
  plan3 - three open recurring mistakes (+ one already learned)  -> the home page shows three mistake cards
  plan1 - one recurring mistake, two weak openings               -> one mistake card and two opening cards
  plan0 - only wins, no errors                                   -> the home page's empty state
"""
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

import chess

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = tempfile.mkdtemp(prefix="chess_test_")
os.environ["CHESS_DATA_DIR"] = DATA_DIR
os.environ.pop("LICHESS_TOKEN", None)
sys.path.insert(0, str(ROOT))

GAME_COLS = ["id", "color", "plies_analyzed", "speed", "score", "result", "line", "eco", "opening", "rating",
             "opp_rating", "created", "moves", "user"]
ERR_COLS = ["id", "ply", "fen_before", "played", "played_san", "best", "eval_before", "eval_after", "win_before",
            "win_after", "drop", "user"]

# opening prefix (white to move at ply 7), the mistake and the better move, in UCI
FAMILIES = {
    "g1": ("Italian Game: Two Knights Defense", "C55", "e4 e5 Nf3 Nc6 Bc4 Nf6", "f3g5", "d2d3"),
    "g2": ("Italian Game: Giuoco Piano", "C50", "e4 e5 Nf3 Nc6 Bc4 Bc5", "f3e5", "c2c3"),
    "g3": ("Queen's Gambit Declined", "D37", "d4 d5 c4 e6 Nc3 Nf6", "c4d5", "c1g5"),
    "g4": ("Zukertort Opening", "A07", "Nf3 d5 g3 Nf6 Bg2 e6", "h2h3", "e1g1"),
    "g5": ("Ruy Lopez", "C60", "e4 e5 Nf3 Nc6 Bb5 a6", "b5c6", "b5a4"),
    "g6": ("English Opening", "A20", "c4 e5 Nc3 Nf6 g3 d5", "c4d5", "d2d4"),
}
_clock = [1_700_000_000_000]
_counter = [0]


def _game(user, fam, mistake, score, rng):
    name, eco, prefix, bad, good = FAMILIES[fam]
    board = chess.Board()
    sans = []
    for san in prefix.split():
        sans.append(san)
        board.push_san(san)
    fen_before = board.fen()
    uci = bad if mistake else good
    move = chess.Move.from_uci(uci)
    if not mistake and not board.is_legal(move):
        move = next(iter(board.legal_moves))
    sans.append(board.san(move))
    played_san = sans[-1]
    board.push(move)
    while len(sans) < 24 and not board.is_game_over():
        m = rng.choice(list(board.legal_moves))
        sans.append(board.san(m))
        board.push(m)
    _counter[0] += 1
    _clock[0] += 3_600_000
    gid = f"{user}{_counter[0]:04d}"
    result = {1.0: "win", 0.5: "draw", 0.0: "loss"}[score]
    game = (gid, "white", 20, "blitz", score, result, " ".join(sans[:12]), eco, name, 1500, 1500, _clock[0],
            " ".join(sans), user)
    err = None
    if mistake:
        err = (gid, 7, fen_before, bad, played_san, good, 80, -120, 55.0, 35.0, 20.0, user)
    return game, err


def _build(con, user, plan):
    """plan: list of (family, [("mistake"|"clean", score), ...]) in chronological order."""
    rng = random.Random(user)
    for fam, games in plan:
        for kind, score in games:
            g, e = _game(user, fam, kind == "mistake", score, rng)
            con.execute(f"INSERT INTO game_results VALUES ({','.join('?' * len(GAME_COLS))})", g)
            if e:
                con.execute(f"INSERT INTO errors VALUES ({','.join('?' * len(ERR_COLS))})", e)


def _create_db():
    con = sqlite3.connect(Path(DATA_DIR) / "cache.sqlite")
    con.execute("CREATE TABLE game_results (id TEXT, color TEXT, plies_analyzed INTEGER, speed TEXT, score REAL, "
                "result TEXT, line TEXT, eco TEXT, opening TEXT, rating INTEGER, opp_rating INTEGER, created INTEGER, "
                "moves TEXT, user TEXT NOT NULL DEFAULT 'yairklo')")
    con.execute("CREATE TABLE errors (id TEXT, ply INTEGER, fen_before TEXT, played TEXT, played_san TEXT, best TEXT, "
                "eval_before INTEGER, eval_after INTEGER, win_before REAL, win_after REAL, \"drop\" REAL, "
                "user TEXT NOT NULL DEFAULT 'yairklo')")
    wins = [("clean", 1.0)] * 6
    losses = [("mistake", 0.0)] * 5
    # clean games first, then the mistakes: the last visit was the mistake -> "repeating"
    rep = lambda fam: (fam, wins + losses)
    learned = ("g4", losses[:3] + [("clean", 1.0)] * 8)   # fixed: 3+ later visits without repeating it
    _build(con, "plan3", [rep("g1"), rep("g2"), rep("g3"), learned])
    _build(con, "yairklo", [rep("g1"), rep("g2"), rep("g3"), learned])   # the default player (practice is "mine" only)
    # one recurring mistake; another opening with mediocre results; the rest wins, so the averages are high
    _build(con, "plan1", [rep("g1"), ("g5", [("clean", 1.0)] * 10),
                          ("g6", [("clean", 0.0)] * 5 + [("clean", 1.0)] * 5)])
    _build(con, "plan0", [("g1", [("clean", 1.0)] * 12), ("g2", [("clean", 1.0)] * 12)])
    con.commit()
    con.close()


_create_db()
