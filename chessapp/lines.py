"""Engine lines for mistake cards: how the mistake gets punished, the better continuation, a short
explanation and the Lichess Study export. Principal variations are cached in SQLite (`pv_v1`) by
(FEN, engine tag), so each position is searched once."""
import atexit
import threading

import chess
import chess.engine
import chess.pgn

from . import config as C
from .analyze import db, engine_tag, fen_key
from .stats import move_label

_engine, _lock = None, threading.Lock()
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
NAMES = {chess.PAWN: ("פיון", "פיונים"), chess.KNIGHT: ("פרש", "פרשים"), chess.BISHOP: ("רץ", "רצים"),
         chess.ROOK: ("צריח", "צריחים"), chess.QUEEN: ("מלכה", "מלכות")}


def _get_engine():
    global _engine
    if _engine is None:
        _engine = chess.engine.SimpleEngine.popen_uci(C.STOCKFISH)
        _engine.configure({"Threads": 1, "Hash": C.ENGINE_HASH})
        # the engine's event-loop thread is not a daemon: close it before the interpreter waits for threads
        getattr(threading, "_register_atexit", atexit.register)(_engine.close)
    return _engine


PV_STORE = 24        # plies of each principal variation kept in the cache
SETTLE_MAX = 16      # never follow a line further than this when waiting for captures to finish


def pv(board: chess.Board):
    """(principal variation as uci list, white-POV centipawns) at the standard depth."""
    if board.is_game_over():
        return [], 0
    con = db()
    with _lock:
        eng = _get_engine()
        tag = engine_tag(eng) + f"|pv{PV_STORE}"
        row = con.execute("SELECT pv, cp FROM pv_v1 WHERE fen=? AND engine=?", (fen_key(board), tag)).fetchone()
        if row:
            return row[0].split(), row[1]
        info = eng.analyse(board, chess.engine.Limit(depth=C.ENGINE_DEPTH))
    moves = [m.uci() for m in info.get("pv", [])][:PV_STORE]
    cp = info["score"].white().score(mate_score=10000)
    con.execute("INSERT OR REPLACE INTO pv_v1 VALUES(?,?,?,?)", (fen_key(board), tag, " ".join(moves), cp))
    con.commit()
    return moves, cp


def balance(board, me):
    """Material balance (pawn units) from `me`'s point of view."""
    return sum(v * (len(board.pieces(pt, me)) - len(board.pieces(pt, not me))) for pt, v in VALUES.items())


def play_line(board, ucis):
    """Plays the legal prefix of `ucis` on a copy; returns (SAN list, final board)."""
    b, sans = board.copy(), []
    for u in ucis:
        m = chess.Move.from_uci(u)
        if m not in b.legal_moves:
            break
        sans.append(b.san(m))
        b.push(m)
    return sans, b


def settled_line(board, ucis):
    """Follow an engine line for at least PV_PLIES plies and then until it is quiet: nobody is in check and the
    next move is not a capture or a check. If the line runs out in the middle of an exchange, ask the engine to
    continue from there. Counting material at a quiet point avoids "a knight is lost" one ply before the recapture."""
    b, sans, queue, last_capture = board.copy(), [], list(ucis), False
    while len(sans) < SETTLE_MAX:
        if not queue:
            if len(sans) >= C.PV_PLIES and not b.is_check() and not last_capture:
                break
            queue = pv(b)[0]
            if not queue:
                break
        m = chess.Move.from_uci(queue[0])
        if m not in b.legal_moves:
            break
        if len(sans) >= C.PV_PLIES and not b.is_check() and not b.is_capture(m) and not b.gives_check(m):
            break
        sans.append(b.san(m))
        last_capture = b.is_capture(m)
        b.push(m)
        queue.pop(0)
    return sans, b


def numbered(sans, first_ply):
    """'8.Nxe5 Nxe5 9.Bxe5' for SANs starting at 1-based ply `first_ply`."""
    return " ".join(move_label(i, s) if i % 2 or i == first_ply else s for i, s in enumerate(sans, first_ply))


def pieces_text(counts):
    """{PAWN: 2, KNIGHT: 1} -> 'פרש ושני פיונים'."""
    parts = []
    for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
        n = counts.get(pt, 0)
        if n:
            one, many = NAMES[pt]
            parts.append(one if n == 1 else ("שני " if pt != chess.QUEEN else "שתי ") + many if n == 2 else f"{n} {many}")
    return " ו".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else (parts[0] if parts else "")


def trade(start, end, me):
    """(pieces `me` lost, pieces the opponent lost) between two boards, equal trades cancelled."""
    lost = {pt: len(start.pieces(pt, me)) - len(end.pieces(pt, me)) for pt in VALUES}
    won = {pt: len(start.pieces(pt, not me)) - len(end.pieces(pt, not me)) for pt in VALUES}
    for pt in VALUES:
        k = min(lost[pt], won[pt])
        lost[pt] -= k
        won[pt] -= k
    # a knight for a bishop is an even trade: cancel minor pieces across the two types
    for mine, theirs in ((chess.KNIGHT, chess.BISHOP), (chess.BISHOP, chess.KNIGHT)):
        k = min(lost[mine], won[theirs])
        lost[mine] -= k
        won[theirs] -= k
    return {k: v for k, v in lost.items() if v > 0}, {k: v for k, v in won.items() if v > 0}


def analysis_url(fen, color):
    return f"https://lichess.org/analysis/standard/{fen.replace(' ', '_')}?color={color}"


def explain(p):
    """Punishment line, better line and a one-sentence explanation for a problem position `p`."""
    me = chess.WHITE if p["color"] == "white" else chess.BLACK
    before = chess.Board(p["fen"])
    after = before.copy()
    after.push(chess.Move.from_uci(p["played_uci"]))
    punish_ucis, cp_after = pv(after)
    punish, end = settled_line(after, punish_ucis)
    better, end_best = settled_line(before, pv(before)[0]) if p["best_uci"] else ([], before)
    lost = balance(before, me) - balance(end, me)
    gain = balance(end_best, me) - balance(before, me)
    mine_cp = cp_after if me == chess.WHITE else -cp_after
    if end.is_checkmate() or mine_cp <= -9000:
        why = "אחרי המסע הזה ליריב יש מט כפוי."
    elif lost >= 1:
        gave, got = trade(before, end, me)
        why = (f"בקו של המנוע ({punish[0] if punish else ''} ואילך, עד שנגמרות ההכאות) הולכים {pieces_text(gave)}"
               + (f" תמורת {pieces_text(got)}" if got else " בלי פיצוי") + ".")
    elif gain >= 1 and mine_cp > -150:
        # "missed chance" only when the move played is not itself losing; otherwise it is simply a bad move
        got, _ = trade(before, end_best, not me)
        why = f"החמצה: המסע המומלץ זוכה ב{pieces_text(got) or 'חומר'}, והמסע ששוחק מפספס את זה (אבל לא מפסיד)."
    elif mine_cp <= -150:
        why = (f"בלי הפסד חומר מיידי, אבל לפי המנוע העמדה נהיית מפסידה: סיכויי הניצחון יורדים מ‑{p['win_before']:.0f}% "
               f"ל‑{p['win_after']:.0f}%.")
    else:
        why = (f"אין הפסד חומר מיידי, אבל העמדה נהיית קשה: סיכויי הניצחון יורדים מ‑{p['win_before']:.0f}% "
               f"ל‑{p['win_after']:.0f}% (מבנה, פיתוח או ביטחון המלך).")
    return dict(punish=numbered(punish, p["ply"] + 1), punish_first=punish[0] if punish else None,
                better=numbered(better, p["ply"]), why=why, lost=lost, gain=gain,
                url=analysis_url(p["fen"], p["color"]))


def study_pgn(problems) -> str:
    """One PGN chapter per problem position, for a Lichess Study: the engine's line is the main line,
    the move actually played is a variation followed by the punishment, plus the opponents' real replies."""
    out = []
    for p in problems:
        x = explain(p)
        before = chess.Board(p["fen"])
        game = chess.pgn.Game()
        game.setup(before)
        for h in ("Date", "Round", "Site"):
            game.headers.pop(h, None)
        game.headers["Event"] = f'{p["opening"]} - {move_label(p["ply"], p["played"])}'
        game.headers["White"], game.headers["Black"] = ("אני", "יריב") if p["color"] == "white" else ("יריב", "אני")
        game.headers["Orientation"] = p["color"]
        game.headers["Annotator"] = "opening analyzer (Stockfish)"
        game.comment = (f'{move_label(p["ply"], p["played"])} שוחק כאן ב-{p["mistakes"]} מתוך {p["reached"]} '
                        f'הפעמים שהעמדה הופיעה. מה עדיף?')
        node = game
        for i, san in enumerate(x["better"].split()):
            mv = before.parse_san(san.split(".")[-1]) if node is game else node.board().parse_san(san.split(".")[-1])
            node = node.add_main_variation(mv, comment="המסע המומלץ (Stockfish)" if i == 0 else "")
        played = game.add_variation(chess.Move.from_uci(p["played_uci"]), comment=f'הטעות. {x["why"]}')
        node = played
        for san in x["punish"].split():
            node = node.add_main_variation(node.board().parse_san(san.split(".")[-1]))
        if played.variations:
            played.variations[0].comment = "העונש לפי המנוע"
        for r in p.get("replies", []):
            if r["san"] != x["punish_first"]:
                try:
                    played.add_variation(played.board().parse_san(r["san"]),
                                         comment=f'היריבים שיחקו כך ב-{r["n"]} משחקים (ציון {r["score"]:.0%})')
                except ValueError:
                    pass
        out.append(str(game))
    return "\n\n".join(out) + "\n"
