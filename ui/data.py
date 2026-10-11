"""Cached loaders, the background engine job, Opening Explorer lookups and the selection helpers."""
import subprocess
import sys
import time

import streamlit as st

from chessapp import config as C
from chessapp.explorer import REASONS, explore, similar_ratings
from chessapp.lines import explain
from chessapp.stats import SORTS, load_results, occurrences, opening_table, prepare, problem_positions

from .common import esc, pct, you
from .ctx import ctx

REASONS_429 = REASONS[429]


def data_stamp(user):
    from chessapp.analyze import db
    con = db()
    try:
        g = con.execute("SELECT count(*), max(created) FROM game_results WHERE user=?", (user,)).fetchone()
        e = con.execute("SELECT count(*) FROM errors WHERE user=?", (user,)).fetchone()[0]
    except Exception:
        return None
    return (*g, e)


@st.cache_data(show_spinner="טוען את המשחקים...")
def get_data(user, stamp, thr):
    return load_results(user, thr)


@st.cache_data(show_spinner=False)
def get_occ(user, stamp):
    return occurrences(get_data(user, stamp, C.ERROR_WIN_DROP)[0])


@st.cache_data(show_spinner="מחשב סטטיסטיקות...")
def get_view(user, stamp, thr, colors: tuple, speeds: tuple):
    """Filtered games (with each game's first error after its opening line), those errors, and the opening tree."""
    games, errors = get_data(user, stamp, thr)
    g, rel, tree = prepare(games[games.color.isin(colors) & games.speed.isin(speeds)], errors)
    t = opening_table(g, errors[errors.id.isin(g.id)], tree)
    if not t.empty:
        t["diff"] = t.score - t.base
    return g, rel, t


@st.cache_data(show_spinner="מחפש טעויות חוזרות...")
def get_problems(user, stamp, thr, colors: tuple, speeds: tuple):
    """All mistakes (position + move played) in the filter, both colours."""
    g, rel, _ = get_view(user, stamp, thr, colors, speeds)
    occ = get_occ(user, stamp)
    occ = occ[occ.id.isin(g.id)]
    return [p for c in colors for p in problem_positions(g, rel, occ, c)]


@st.cache_data(show_spinner="מחשב קווים במנוע...")
def get_explain(fen, played_uci, best_uci, color, ply, win_before, win_after):
    return explain(dict(fen=fen, played_uci=played_uci, best_uci=best_uci, color=color, ply=ply,
                        win_before=win_before, win_after=win_after))


def explain_p(p):
    return get_explain(p["fen"], p["played_uci"], p["best_uci"], p["color"], p["ply"], p["win_before"], p["win_after"])


# ---------------------------------------------------------------- background engine analysis
def job_log(user):
    return C.DATA / f"analyze_{user}.log"


def start_analysis(user):
    log = open(job_log(user), "w", encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen([sys.executable, "-m", "chessapp.analyze", user], cwd=C.ROOT, stdout=log,
                     stderr=subprocess.STDOUT, creationflags=flags)


def pid_alive(pid):
    """Whether a process exists (without signalling it: os.kill on Windows would terminate it)."""
    if sys.platform == "win32":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    import os
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def job_state(user):
    """('none'|'running'|'done'|'failed', done, total) from the job's log file and whether its process lives."""
    f = job_log(user)
    if not f.exists():
        return "none", 0, 0
    text = f.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    prog = [l.split()[1].split("/") for l in lines if l.startswith("PROGRESS")]
    k, n = map(int, prog[-1]) if prog else (0, 0)
    if "DONE" in text:
        return "done", k, n
    if "Traceback" in text:
        return "failed", k, n
    pid = next((int(l.split()[1]) for l in lines if l.startswith("PID ")), None)
    if pid is None:  # just started, the process has not written its PID yet
        return ("running" if time.time() - f.stat().st_mtime < 60 else "failed"), k, n
    return ("running" if pid_alive(pid) else "failed"), k, n



def explorer(fen, rating):
    """Explorer lookup; successes are cached in SQLite. After a 429 no request is sent for a minute, so a long
    list of cards does not keep hitting the rate limit (and failures are not cached for longer than that)."""
    if time.time() < st.session_state.get("explorer_blocked_until", 0):
        return None, REASONS_429
    ex, reason = explore(fen, rating)
    if reason == REASONS_429:
        st.session_state.explorer_blocked_until = time.time() + 60
    return ex, reason


LEVEL_MIN_GAMES = 100   # fewer Lichess games than this for the move played: no verdict


def level_range(rating):
    b = [int(x) for x in similar_ratings(rating).split(",")]
    return f"{b[0]}–{b[-1] + 200}"


def level_view(p):
    """How the move played and the engine's move score in Lichess games at the player's rating (Opening Explorer).
    works = the move played is common enough and scores at least 50% and at least as well as the engine's move."""
    if not C.lichess_token():
        return None
    rating = int(ctx.fdf[ctx.fdf.color == p["color"]].rating.median())
    ex, reason = explorer(p["fen"], rating)
    if not ex:
        return {"error": reason}
    total = ex["white"] + ex["draws"] + ex["black"]
    moves = {}
    for m in ex["moves"]:
        t = m["white"] + m["draws"] + m["black"]
        if t:
            mine = m["white"] if p["color"] == "white" else m["black"]
            moves[m["san"]] = {"n": t, "share": t / total if total else 0, "score": (mine + m["draws"] / 2) / t}
    pl, be = moves.get(p["played"]), moves.get(p["best_san"])
    works = bool(pl and pl["n"] >= LEVEL_MIN_GAMES and pl["score"] >= 0.5 and (be is None or pl["score"] >= be["score"]))
    return {"ex": ex, "played": pl, "best": be, "works": works, "level": level_range(rating)}


def level_html(p, lv):
    """The practical verdict shown on the card, next to the engine's verdict."""
    if not lv or "error" in lv:
        return ""
    pl, be, played, best = lv["played"], lv["best"], esc(p["played"]), esc(p["best_san"] or "?")
    where = f"שחקנים בדירוג {lv['level']} ב־Lichess (בליץ ורפיד)"
    if not pl:
        return (f'<div class="level"><b>ברמה {you("שלך", "של השחקן")}:</b> {where} כמעט לא משחקים כאן '
                f'<span class="ltr">{played}</span>, אז אין נתון מעשי שסותר את המנוע.</div>')
    best_txt = (f'לעומת {pct(be["score"])} עם <span class="ltr">{best}</span> ({be["n"]:,} משחקים)' if be
                else f'(<span class="ltr">{best}</span> של המנוע כמעט לא משוחק ברמה הזו)')
    stats = (f'{where} משחקים כאן <span class="ltr">{played}</span> ב‑{pct(pl["share"])} מהמשחקים '
             f'({pl["n"]:,}) ומשיגים {pct(pl["score"])}, {best_txt}.')
    if lv["works"]:
        own = (f' {you("אצלך", "אצל השחקן")} המסע השיג {pct(p["score"])} ב‑{p["count"]} משחקים'
               + (", כך שכנראה כדאי ללמוד את ההמשך שלו ולא לוותר עליו." if p["score"] < pl["score"] - 0.05 else "."))
        return (f'<div class="level good"><b>בפועל זה עובד ברמה {you("שלך", "הזו")}:</b> {stats} '
                f'Stockfish צודק בתיאוריה, אבל ברמה הזו היריבים בדרך כלל לא מוצאים את ההפרכה.{own}</div>')
    return f'<div class="level"><b>גם ברמה {you("שלך", "הזו")} המנוע צודק:</b> {stats}</div>'


def tr_key(p):
    return f'{p["color"]}|{p["key"]}|{p["played"]}'


def recurring(items):
    """Practice and focus use only mistakes that really repeat (3+ games); 2+ when there are none."""
    rec = [p for p in items if p["count"] >= C.MIN_PROBLEM_GAMES]
    return rec or [p for p in items if p["count"] >= 2]


def by_cost(items):
    """Open mistakes first, the ones that cost the most points first."""
    return sorted(items, key=lambda p: (p["status"] == "learned", -p["cost"], -p["count"]))


def list_mistakes():
    """The mistakes the Mistakes screen walks through: every mistake that repeated at least twice."""
    return by_cost([p for p in ctx.probs if p["count"] >= 2])


def find_mistake(key):
    return next((p for p in ctx.probs if tr_key(p) == key), None)
