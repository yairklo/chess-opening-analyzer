"""Streamlit dashboard: opening analysis for a Lichess player (Hebrew, RTL)."""
import html
import random
import subprocess
import sys
import time

import altair as alt
import chess
import chess.svg
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.analyze import build_results, users
from chessapp.fetch_games import FetchError, fetch
from chessapp.stats import (SORTS, load_results, move_label, occurrences, opening_table, overall, prepare,
                            problem_positions, san_of)
from chessapp.explorer import explore, similar_ratings
from chessapp.lines import explain, study_pgn

st.set_page_config(page_title="ניתוח פתיחות", page_icon="♞", layout="wide")

COLORS = {"white": "לבן", "black": "שחור"}
WITH_COLOR = {"white": "עם הלבנים", "black": "עם השחורים"}
SPEEDS = {"bullet": "בוליט", "blitz": "בליץ", "rapid": "רפיד", "classical": "קלאסי", "correspondence": "התכתבות"}
RESULTS = {"win": "ניצחון", "draw": "תיקו", "loss": "הפסד"}
STATUS_ME = {  # learning status -> (label, tone, explanation)
    "repeating": ("עדיין חוזרת", "red", "בפעם האחרונה שהגעת לעמדה הזו שיחקת שוב את אותו מסע."),
    "improving": ("בדרך לתיקון", "amber", "בביקורים האחרונים לא חזרת על הטעות, אבל עוד מוקדם לקבוע."),
    "learned": ("נלמדה", "green", f"מאז הטעות האחרונה הגעת לעמדה {C.LEARN_FIXED_AFTER}+ פעמים ולא חזרת עליה."),
    "few": ("מעט נתונים", "gray", f"הגעת לעמדה הזו פחות מ‑{C.LEARN_MIN_REACHED} פעמים, אז עוד אי אפשר לקבוע מגמה."),
}
STATUS_OTHER = {
    "repeating": ("עדיין חוזרת", "red", "בפעם האחרונה שהעמדה הופיעה שוחק שוב אותו מסע."),
    "improving": ("בדרך לתיקון", "amber", "בביקורים האחרונים בעמדה הטעות לא חזרה, אבל עוד מוקדם לקבוע."),
    "learned": ("נלמדה", "green", f"מאז הטעות האחרונה העמדה הופיעה {C.LEARN_FIXED_AFTER}+ פעמים והטעות לא חזרה."),
    "few": ("מעט נתונים", "gray", f"פחות מ‑{C.LEARN_MIN_REACHED} ביקורים בעמדה, אז עוד אי אפשר לקבוע מגמה."),
}
STATUS = STATUS_ME
CONF = {"high": ("ודאות גבוהה", "green"), "mid": ("ודאות בינונית", "amber"), "low": ("ייתכן מקרי", "gray")}
RED, GREEN = "#dc2626d0", "#16a34ad0"
LRM = "‎"  # keeps move sequences left-to-right inside RTL table cells

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600&display=swap');
:root{--ink:#111827;--muted:#6b7280;--soft:#9ca3af;--line:#e5e7eb;--card:#fff;--bg:#f6f7f9;
--blue:#2563eb;--blue-50:#eff6ff;--green:#15803d;--green-50:#ecfdf3;--red:#dc2626;--red-50:#fef2f2;
--amber:#b45309;--amber-50:#fffbeb;--gray-50:#f3f4f6;}
html,body,.stApp,[data-testid="stSidebar"],button,input,textarea,select,p,li,label{font-family:'Heebo',system-ui,sans-serif!important;}
[data-testid="stMain"],[data-testid="stSidebar"]{direction:rtl;text-align:right;}
[data-testid="stMainBlockContainer"]{max-width:1240px;padding-top:2.2rem;padding-bottom:4rem;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stAppViewContainer"]{flex-direction:row-reverse;}
h1,h2,h3{font-family:'Heebo',sans-serif!important;letter-spacing:-.01em;}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:.5rem;}
[data-testid="stCaptionContainer"]{color:var(--muted);}
[class*="st-key-card"]{background:var(--card);border-radius:16px!important;box-shadow:0 1px 2px rgba(16,24,40,.04);}
[data-testid="stImage"] img{border-radius:6px;}
[data-testid="stVegaLiteChart"]{direction:ltr;}  /* RTL flips SVG text anchors: labels would overlap the bars */
.ltr{direction:ltr;unicode-bidi:isolate;display:inline-block;font-family:'JetBrains Mono',monospace;font-size:.92em;}
.muted{color:var(--muted);} .small{font-size:.85rem;}

.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;margin-bottom:1.2rem;}
.hero .eyebrow{color:var(--blue);font-weight:600;font-size:.85rem;letter-spacing:.02em;}
.hero h1{font-size:2.1rem;font-weight:800;margin:.1rem 0 .3rem;padding:0;color:var(--ink);}
.hero p{color:var(--muted);margin:0;font-size:.98rem;}
.rating{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px 18px;text-align:center;min-width:140px;}
.rating .k{font-size:.78rem;color:var(--muted);} .rating .v{font-size:1.6rem;font-weight:800;line-height:1.2;}
.up{color:var(--green);font-size:.85rem;font-weight:600;} .down{color:var(--red);font-size:.85rem;font-weight:600;}

.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;height:100%;min-height:150px;}
.kpi .k{color:var(--muted);font-size:.88rem;font-weight:500;}
.kpi .v{font-size:2.1rem;font-weight:800;line-height:1.15;margin-top:6px;color:var(--ink);}
.kpi .v.red{color:var(--red);} .kpi .v.green{color:var(--green);}
.kpi .s{color:var(--muted);font-size:.84rem;margin-top:8px;line-height:1.5;}

.wdl{display:flex;height:8px;border-radius:99px;overflow:hidden;background:var(--gray-50);margin-top:12px;direction:rtl;}
.wdl span{display:block;height:100%;} .wdl .w{background:#22c55e;} .wdl .d{background:#cbd5e1;} .wdl .l{background:#ef4444;}
.legend{display:flex;gap:14px;margin-top:8px;font-size:.8rem;color:var(--muted);flex-wrap:wrap;}
.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:5px;}

.sec{margin:2.2rem 0 .9rem;} .sec h3{font-size:1.25rem;font-weight:700;margin:0;padding:0;color:var(--ink);}
.sec p{color:var(--muted);margin:.25rem 0 0;font-size:.93rem;}

.chip{display:inline-flex;align-items:center;gap:6px;padding:2px 10px 2px 10px;border-radius:99px;font-size:.78rem;font-weight:600;
background:var(--gray-50);color:#374151;border:1px solid var(--line);}
.chip i{width:10px;height:10px;border-radius:50%;display:inline-block;border:1.5px solid #374151;}
.chip-white i{background:#fff;} .chip-black i{background:#111827;}
.badge{display:inline-flex;align-items:center;padding:2px 10px;border-radius:99px;font-size:.78rem;font-weight:600;white-space:nowrap;}
.b-red{background:var(--red-50);color:var(--red);} .b-green{background:var(--green-50);color:var(--green);}
.b-amber{background:var(--amber-50);color:var(--amber);} .b-gray{background:var(--gray-50);color:var(--muted);}
.b-blue{background:var(--blue-50);color:var(--blue);}

.card-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;}
.card-h .t{font-weight:700;font-size:1.08rem;color:var(--ink);}
.rank{font-weight:800;color:var(--blue);font-size:1.05rem;}

.moves{direction:ltr;text-align:left;font-family:'JetBrains Mono',monospace;font-size:.88rem;line-height:2.1;color:#374151;}
.moves .n{color:var(--soft);margin:0 2px 0 6px;}
.moves{word-break:normal;overflow-wrap:normal;} .moves .u{white-space:nowrap;display:inline-block;}
.st-key-add_name input{direction:ltr;text-align:left;}
.level{background:var(--gray-50);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:.88rem;margin:8px 0;}
.level.good{background:var(--blue-50);border-color:#bfdbfe;color:#1e3a8a;}
.why{background:var(--amber-50);border:1px solid #fde68a;border-radius:10px;padding:8px 12px;font-size:.88rem;color:#78350f;margin:8px 0;}
.lines{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:.86rem;margin:8px 0;align-items:baseline;}
.lines .k{color:var(--muted);white-space:nowrap;}
.replies{width:100%;font-size:.84rem;border-collapse:collapse;margin-top:4px;} .replies td,.replies th{padding:3px 6px;text-align:right;border-bottom:1px solid var(--gray-50);}
.replies th{color:var(--muted);font-weight:500;}
.moves .m{padding:2px 5px;border-radius:5px;}
.moves .cur{background:#dbeafe;color:#1e40af;font-weight:600;}
.moves .err{background:var(--red-50);color:var(--red);font-weight:700;outline:1px solid #fecaca;}
.moves .dim{color:#c3c7cf;}

.cmp{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0;}
.cmp>div{border-radius:12px;padding:10px 14px;}
.cmp .bad{background:var(--red-50);border:1px solid #fecaca;} .cmp .good{background:var(--green-50);border:1px solid #bbf7d0;}
.cmp .k{font-size:.78rem;color:var(--muted);} .cmp .v{font-family:'JetBrains Mono',monospace;font-size:1.35rem;font-weight:700;direction:ltr;text-align:right;}
.cmp .bad .v{color:var(--red);} .cmp .good .v{color:var(--green);}
.cmp .plain{background:var(--gray-50);border:1px solid var(--line);} .cmp .plain .v{color:var(--soft);}
.opts .v{text-align:center;font-size:1.1rem;}
[class*="st-key-opt_"] button{font-family:'JetBrains Mono',monospace!important;font-size:1.1rem;font-weight:600;min-height:3rem;}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:10px 0;}
.stats>div{background:var(--gray-50);border-radius:10px;padding:8px 12px;}
.stats.s3{grid-template-columns:repeat(3,1fr);gap:6px;} .stats.s3>div{padding:8px 10px;}
.stats .k{font-size:.76rem;color:var(--muted);} .stats .v{font-weight:700;font-size:1.05rem;color:var(--ink);}
.note{font-size:.84rem;color:var(--muted);margin-top:6px;line-height:1.55;}
.links a{display:inline-block;margin:2px 0 2px 6px;padding:1px 8px;border-radius:6px;background:var(--blue-50);color:var(--blue)!important;
text-decoration:none;font-size:.78rem;font-family:'JetBrains Mono',monospace;}
.crow{display:flex;justify-content:space-between;gap:16px;padding:8px 0;border-top:1px solid var(--gray-50);font-size:.9rem;}
.crow .ck{color:var(--muted);white-space:nowrap;} .crow .cv{font-weight:600;text-align:left;color:var(--ink);}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:14px;padding:28px;text-align:center;color:var(--muted);}
.gloss dt{font-weight:700;margin-top:10px;font-size:.88rem;} .gloss dd{margin:2px 0 0;color:var(--muted);font-size:.84rem;line-height:1.5;}
.brand{font-weight:800;font-size:1.15rem;margin:.2rem 0 1rem;} .brand span{color:var(--blue);}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- data
# every cached function takes (user, stamp); the stamp changes when that player's data changes
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


@st.fragment(run_every=3)
def analysis_progress(user):
    state, k, n = job_state(user)
    if state == "running":
        st.progress(k / n if n else 0.0, text=f"Stockfish מנתח: {k} מתוך {n or '?'} משחקים")
        st.caption("אפשר להמשיך לעבוד בינתיים – הטעויות יופיעו כשהניתוח יסתיים.")
    else:
        st.rerun(scope="app")


def engine_panel(user, has_errors):
    """Sidebar block: engine analysis status for the selected player."""
    state, _, _ = job_state(user)
    if state == "running":
        analysis_progress(user)
    elif has_errors:
        st.caption(f"✓ נותח ב־Stockfish (עומק {C.ENGINE_DEPTH}).")
    else:
        if state == "failed":
            st.error("הניתוח נכשל. אפשר לנסות שוב.")
        n = stamp[0] if stamp else 0
        st.caption(f"הטעויות בפתיחה עוד לא נותחו. ניתוח {n:,} משחקים לוקח בערך {max(1, round(n * 0.65 / 60))} דקות.")
        st.button("נתח טעויות ב־Stockfish", on_click=start_analysis, args=(user,), icon=":material/memory:",
                  width="stretch", key="run_engine")


def add_player(name, n, run_engine=True):
    name = name.strip()
    try:
        with st.status(f"מוריד את {n} המשחקים האחרונים של {name}...", expanded=True) as box:
            line = st.empty()
            got = fetch(name, refresh=True, max_games=n, on_progress=lambda k: line.write(f"{k} משחקים..."))
            line.write(f"{got} משחקים הורדו. בונה את עץ הפתיחות...")
            build_results(name)
            if run_engine:
                start_analysis(name.lower())
                line.write(f"{got} משחקים הורדו. ניתוח הטעויות ב־Stockfish התחיל ברקע.")
            box.update(label=f"{name} נטען", state="complete")
    except FetchError as e:
        st.error({"not found": f"לא נמצא ב־Lichess שחקן בשם '{name}'.", "valid": "שם המשתמש לא תקין."}.get(
            next((k for k in ("not found", "valid") if k in str(e)), ""), f"לא נמצאו משחקים עבור '{name}'."))
        return
    except Exception as e:  # network problems, rate limits...
        st.error(f"ההורדה נכשלה: {e}")
        return
    st.session_state.pending_user = name.lower()
    st.rerun()


@st.cache_data(show_spinner=False, ttl=600)  # failures are retried after 10 minutes
def explorer(fen, rating):
    return explore(fen, rating)


# ---------------------------------------------------------------- html helpers
def esc(t):
    return html.escape(str(t))


def en(t):
    """Left-to-right text (opening names, moves) isolated inside a right-to-left sentence."""
    return f'<bdi dir="ltr">{esc(t)}</bdi>'


def clip(text, n):
    """Shorten at a word boundary, with the ellipsis at the end of the (left-to-right) text."""
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(":,/ ")
    return cut + "…"


def tail_moves(group, chars=24):
    """The last moves of a line that fit in `chars`, cut at a move boundary: '…3.Bc4 Nf6 4.d3'."""
    toks = group.split()
    for k in range(len(toks)):
        part = " ".join(move_label(i, m) if i % 2 or i == k + 1 else m for i, m in enumerate(toks[k:], k + 1))
        if len(part) <= chars or k == len(toks) - 1:
            return ("…" if k else "") + part
    return ""


def md(h):
    st.markdown(h, unsafe_allow_html=True)


def pct(x):
    return f"{x:.0%}"


def fmt_date(v):
    return (pd.to_datetime(v) if isinstance(v, str) else pd.to_datetime(int(v), unit="ms")).strftime("%d.%m.%Y")


def chip(color):
    return f'<span class="chip chip-{color}"><i></i>{COLORS[color]}</span>'


def badge(status):
    label, tone, _ = STATUS[status]
    return f'<span class="badge b-{tone}">{label}</span>'


def wdl(w, d, l, legend=True):
    bar = (f'<div class="wdl"><span class="w" style="width:{w:.1%}"></span><span class="d" style="width:{d:.1%}"></span>'
           f'<span class="l" style="width:{l:.1%}"></span></div>')
    if legend:
        bar += (f'<div class="legend"><span><i style="background:#22c55e"></i>ניצחון {pct(w)}</span>'
                f'<span><i style="background:#cbd5e1"></i>תיקו {pct(d)}</span>'
                f'<span><i style="background:#ef4444"></i>הפסד {pct(l)}</span></div>')
    return bar


def kpi(label, value, sub="", tone=""):
    return f'<div class="kpi"><div class="k">{label}</div><div class="v {tone}">{value}</div><div class="s">{sub}</div></div>'


def section(title, sub=""):
    md(f'<div class="sec"><h3>{title}</h3>{f"<p>{sub}</p>" if sub else ""}</div>')


def empty(text):
    md(f'<div class="empty">{text}</div>')


def moves_html(moves, upto=None, cur=None, err=None):
    """Numbered move list. `cur` / `err` are 1-based plies to highlight; plies after `upto` are dimmed."""
    out = []
    for i, san in enumerate(moves, 1):
        cls = "err" if i == err else "cur" if i == cur else "dim" if upto is not None and i > upto else ""
        num = f'<span class="n">{(i + 1) // 2}.</span>' if i % 2 else ""
        out.append(f'<span class="u">{num}<span class="m {cls}">{esc(san)}</span></span> ')  # a move never wraps
    return f'<div class="moves">{"".join(out) or "<span class=n>עמדת הפתיחה</span>"}</div>'


def game_links(ids, color, ply, n=10):
    return '<div class="links">' + "".join(
        f'<a href="https://lichess.org/{i}/{color}#{ply}" target="_blank">{i}</a>' for i in ids[:n]) + "</div>"


BOARD_COLORS = {"square light": "#f0d9b5", "square dark": "#b58863", "square light lastmove": "#cdd26a",
                "square dark lastmove": "#aaa23a", "margin": "#ffffff", "coord": "#8b8f98",
                "inner border": "#b58863", "outer border": "#ffffff"}


def board_svg(board, color, last=None, arrows=(), size=460):
    ar = []
    for uci, clr in arrows:
        if uci:
            m = chess.Move.from_uci(uci)
            ar.append(chess.svg.Arrow(m.from_square, m.to_square, color=clr))
    check = board.king(board.turn) if board.is_check() else None
    return chess.svg.board(board, arrows=ar, lastmove=last, check=check, size=size, colors=BOARD_COLORS,
                           orientation=chess.WHITE if color == "white" else chess.BLACK)


def arrow_legend():
    return (f'<div class="legend"><span><i style="background:#dc2626"></i>{you("המסע ששיחקת", "המסע ששוחק")}</span>'
            '<span><i style="background:#16a34a"></i>המסע המומלץ</span></div>')


def position_at(moves, ply):
    """Board after `ply` half-moves, plus the last move (for highlighting)."""
    b, last = chess.Board(), None
    for san in moves[:ply]:
        last = b.push_san(san)
    return b, last


def explorer_html(ex, color):
    tot = ex["white"] + ex["draws"] + ex["black"]
    rows = []
    for m in ex["moves"]:
        t = m["white"] + m["draws"] + m["black"]
        mine = m["white"] if color == "white" else m["black"]
        rows.append(f'<tr><td class="ltr">{esc(m["san"])}</td><td>{t:,}</td><td>{pct(t / tot) if tot else ""}</td>'
                    f'<td>{pct((mine + m["draws"] / 2) / t) if t else ""}</td></tr>')
    return (f'<div class="note"><b>מה משחקים שחקנים ברמה {you("שלך", "דומה")} (Lichess)</b></div>'
            '<table style="width:100%;font-size:.84rem"><tr><th>מסע</th><th>משחקים</th><th>שכיחות</th><th>אחוז נקודות</th></tr>'
            + "".join(rows) + "</table>")


def rtl_table(view, column_config=None, **kw):
    """st.dataframe renders left-to-right; reverse the columns so the first one sits on the right."""
    cfg = {c: st.column_config.TextColumn(alignment="right") for c in view.columns if not pd.api.types.is_numeric_dtype(view[c])}
    cfg.update(column_config or {})
    return st.dataframe(view[view.columns[::-1]], hide_index=True, width="stretch", column_config=cfg, **kw)


# ---------------------------------------------------------------- navigation helpers
def go(page, op_key=None):
    st.session_state.page = page
    if op_key:
        st.session_state.op_key = op_key
        st.session_state.op_nonce = st.session_state.get("op_nonce", 0) + 1


def set_state(k, v):
    st.session_state[k] = v


# ---------------------------------------------------------------- player, load + filters
players = users()
if not players:
    st.error("לא נמצאו תוצאות ניתוח. הריצו קודם בטרמינל: python run_all.py")
    st.stop()
if "pending_user" in st.session_state:  # set by add_player before the selectbox exists
    st.session_state.user = st.session_state.pop("pending_user")
if st.session_state.get("user") not in players:
    st.session_state.user = players[0]

with st.sidebar:
    md('<div class="brand">♞ ניתוח <span>פתיחות</span></div>')
    user = st.selectbox("שחקן", players, key="user",
                        format_func=lambda u: f"{u} (אני)" if u == C.USER.lower() else u)
    with st.popover("הוספת שחקן מ־Lichess", icon=":material/person_add:", width="stretch"):
        with st.form("add_player", border=False, clear_on_submit=True):
            name = st.text_input("שם משתמש ב־Lichess", placeholder="DrNykterstein", key="add_name")
            n_games = st.segmented_control("כמה משחקים אחרונים", [200, 500, 1000], default=500)
            run_engine = st.checkbox("לנתח מיד גם את הטעויות ב־Stockfish (ברקע)", True)
            st.caption("ההורדה לוקחת בערך דקה לכל 500 משחקים, ועץ הפתיחות והחולשות מוכנים מיד אחריה. "
                       "ניתוח הטעויות לוקח עוד כ‑5 דקות לכל 500 משחקים, ואפשר להמשיך לעבוד בזמן שהוא רץ.")
            go_add = st.form_submit_button("הורד ונתח", type="primary", width="stretch")
        if go_add and name.strip():
            add_player(name, n_games or 500, run_engine)

me = user == C.USER.lower()
STATUS = STATUS_ME if me else STATUS_OTHER
stamp = data_stamp(user)
analyzed = bool(stamp and stamp[2])


def you(mine, theirs):
    """Second person for the default player, the player's name (or a neutral form) for anyone else."""
    return mine if me else theirs


with st.sidebar:
    engine_panel(user, analyzed)
    st.divider()
    pick = st.segmented_control(you("אני משחק עם", "צבע"), ["all", "white", "black"], default="all", key="f_color",
                                format_func={"all": "שני הצבעים", **COLORS}.get, width="stretch")
    colors = [pick] if pick in COLORS else list(COLORS)
    thr = st.select_slider("רגישות: מה נחשב טעות", C.ERROR_WIN_DROP_CHOICES, value=C.ERROR_WIN_DROP, key="thr",
                           format_func=lambda v: f"ירידה של {v}%",
                           help="בכמה נקודות אחוז צריכים לרדת סיכויי הניצחון כדי שמסע ייחשב טעות. נמוך = יותר טעויות "
                                "(גם עדינות), גבוה = רק טעויות ברורות. ברירת המחדל 12%. השינוי מיידי, בלי להריץ שוב את המנוע.")
    df, all_errors = get_data(user, stamp, thr)
    avail = [s for s in SPEEDS if s in set(df.speed)] + sorted(set(df.speed) - set(SPEEDS))
    if len(avail) > 1:
        speeds = st.multiselect("קצב משחק", avail, avail, format_func=lambda s: SPEEDS.get(s, s), key=f"speeds_{user}")
    else:
        speeds = avail
        st.caption(f"כל המשחקים בקצב {SPEEDS.get(avail[0], avail[0])}.")
    st.divider()
    with st.expander("איך לקרוא את הנתונים", icon=":material/help:"):
        md(f"""<dl class="gloss">
<dt>אחוז נקודות</dt><dd>ניצחון = נקודה, תיקו = חצי. 50% = מאזן שוויוני.</dd>
<dt>סיכויי ניצחון</dt><dd>הערכת המנוע מתורגמת לסיכוי (0–100%) לפי הנוסחה של Lichess. 50% = עמדה שקולה.</dd>
<dt>טעות בפתיחה</dt><dd>מסע ב‑{C.ANALYZE_PLIES // 2} המסעים הראשונים שלך שמוריד את סיכויי הניצחון ב‑{thr}% או יותר (ניתן לשינוי למעלה). מסע שהוא המסע של המנוע אף פעם לא נחשב טעות.
מסעים שהם חלק מקו הפתיחה שאתה משחק קבוע (למשל גמביט) לא נחשבים טעות.</dd>
<dt>נקודות שאבדו</dt><dd>כמה נקודות הפתיחה עלתה לך לעומת הממוצע שלך באותו צבע: משחקים × (הממוצע − אחוז הנקודות בפתיחה).</dd>
<dt>פתיחה בעייתית</dt><dd>אחוז נקודות נמוך ב‑{C.TOXIC_MARGIN:.0%} לפחות מהממוצע שלך באותו צבע, טעות עד מסע {C.EARLY_ERROR_MOVE} ב‑{C.EARLY_ERROR_SHARE:.0%} או יותר מהמשחקים,
וגם אותה טעות בדיוק ב‑{C.MIN_PROBLEM_GAMES} משחקים לפחות.</dd>
<dt>עץ הפתיחות</dt><dd>כל שורה כוללת את כל המשחקים שהתחילו ברצף הזה, כולל ההמשכים שלה.</dd>
<dt>טעות חוזרת</dt><dd>אותו מסע שגוי באותה עמדה ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר.</dd>
<dt>טעות שנלמדה</dt><dd>{STATUS["learned"][2]}</dd>
</dl>""")
    st.caption(f"ניתוח המנוע: {en('Stockfish')} בעומק {C.ENGINE_DEPTH} קבוע לכל עמדה. "
               f"פתיחה מוצגת רק אם שוחקה {C.MIN_GROUP_GAMES}+ פעמים.", unsafe_allow_html=True)

if df[df.color.isin(colors) & df.speed.isin(speeds)].empty:
    empty("אין משחקים שמתאימים לסינון. שנו את הבחירה בסרגל הצד.")
    st.stop()
fdf, rel, tbl = get_view(user, stamp, thr, tuple(colors), tuple(speeds))
probs = get_problems(user, stamp, thr, tuple(colors), tuple(speeds))


def node_games(op):
    """All filtered games that start with the node's moves (the node row sums its whole subtree)."""
    pre = op.group.split()
    return fdf[(fdf.color == op.color) & fdf.line.str.split().map(lambda s: s[:len(pre)] == pre)]

# ---------------------------------------------------------------- header
sel = df[df.speed.isin(speeds)]
main_speed = sel.speed.mode().iat[0]  # ratings are per speed: chart the most played one
by_time = sel[sel.speed == main_speed].sort_values("created")
first_d, last_d = sel.created.min(), sel.created.max()
r_now, r_change = int(by_time.rating.iat[-1]), int(by_time.rating.iat[-1] - by_time.rating.iat[0])
trend = f'<span class="{"up" if r_change >= 0 else "down"}">{"▲" if r_change >= 0 else "▼"} {abs(r_change)} בתקופה</span>'
speed_txt = f"משחקי {SPEEDS.get(speeds[0], speeds[0])}" if len(speeds) == 1 else "משחקים"
engine_txt = (f"{C.ANALYZE_PLIES // 2} המסעים הראשונים בכל משחק נבדקו במנוע Stockfish" if analyzed
              else "הטעויות עוד לא נותחו במנוע (אפשר להפעיל בסרגל הצד)")
md(f"""<div class="hero"><div><div class="eyebrow">LICHESS · {esc(user)}</div><h1>{you("ניתוח הפתיחות שלך", f"ניתוח הפתיחות של {esc(user)}")}</h1>
<p>{len(fdf):,} {speed_txt} · {fmt_date(first_d)} – {fmt_date(last_d)} · {engine_txt}</p></div>
<div class="rating"><div class="k">דירוג {SPEEDS.get(main_speed, main_speed)} נוכחי</div><div class="v">{r_now}</div>{trend}</div></div>""")

PAGES = {"overview": "סקירה", "weak": "נקודות חולשה", "openings": you("הפתיחות שלי", "פתיחות"),
         "mistakes": "טעויות חוזרות", **({"practice": "תרגול"} if me else {})}
if st.session_state.get("page") not in PAGES:
    st.session_state.page = "overview"
page = st.segmented_control("ניווט", list(PAGES), key="page", format_func=PAGES.get, label_visibility="collapsed")
if page is None:  # clicking the active segment deselects it; stay where we were
    page = st.session_state.get("last_page", "overview")
st.session_state.last_page = page


# ---------------------------------------------------------------- overview
def color_card(c):
    s = fdf[fdf.color == c]
    t = tbl[(tbl.color == c) & (tbl.depth > 0)] if not tbl.empty else tbl
    best = t.sort_values("score", ascending=False).iloc[0] if len(t) else None
    worst = t.sort_values("cost", ascending=False).iloc[0] if len(t) else None
    rows = [("משחקים", f"{len(s):,}"), ("טעות בפתיחה", f"ב‑{s.first_error_ply.notna().mean():.0%} מהמשחקים")]
    if best is not None:
        rows.append(("הפתיחה הכי מוצלחת", f'{en(clip(best.opening, 34))} · {pct(best.score)}'))
        rows.append(("הפתיחה שהכי עולה לך", f'{en(clip(worst.opening, 34))} · {pct(worst.score)}'))
    body = "".join(f'<div class="crow"><span class="ck">{k}</span><span class="cv">{v}</span></div>' for k, v in rows)
    return (f'<div class="kpi color-card"><div class="card-h">{chip(c)}<span class="t">{WITH_COLOR[c]}</span></div>'
            f'<div class="v">{pct(s.score.mean())}</div><div class="s">אחוז נקודות</div>'
            f'{wdl((s.result == "win").mean(), (s.result == "draw").mean(), (s.result == "loss").mean())}'
            f'<div style="margin-top:10px">{body}</div></div>')


def chart_rating():
    d = by_time.assign(date=pd.to_datetime(by_time.created, unit="ms"))
    d = d.groupby(d.date.dt.normalize()).rating.last().reset_index()
    y = alt.Y("rating:Q", title=None, scale=alt.Scale(zero=False, padding=20))
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m", tickCount=6))
    base_c = alt.Chart(d)
    ch = (base_c.mark_line(color="#2563eb", strokeWidth=2.5)
          + base_c.mark_point(color="#2563eb", filled=True, size=26, opacity=0)
          .encode(tooltip=[alt.Tooltip("date:T", title="תאריך", format="%d.%m.%Y"), alt.Tooltip("rating:Q", title="דירוג")]))
    return ch.encode(x=x, y=y).properties(height=230)


def chart_error_moves():
    e = fdf.first_error_move.dropna().astype(int).value_counts().reindex(range(1, C.ANALYZE_PLIES // 2 + 1), fill_value=0)
    d = pd.DataFrame({"move": e.index, "games": e.values, "share": e.values / len(fdf)})
    return alt.Chart(d).mark_bar(color="#2563eb", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("move:O", title="מסע", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("games:Q", title=None),
        tooltip=[alt.Tooltip("move:O", title="מסע"), alt.Tooltip("games:Q", title="משחקים"),
                 alt.Tooltip("share:Q", title="מכלל המשחקים", format=".0%")]).properties(height=230)


def focus_openings(n):
    """Openings with the largest cost, skipping any node whose ancestor or descendant was already picked
    (tree rows include their children, so overlapping picks would count the same games twice)."""
    picked = []
    if tbl.empty:
        return tbl
    for r in tbl[tbl.cost > 0].sort_values("cost", ascending=False).itertuples():
        if all(r.color != q.color or not (r.group.startswith(q.group + " ") or q.group.startswith(r.group + " "))
               for q in picked):
            picked.append(r)
        if len(picked) == n:
            break
    return tbl[tbl.key.isin([q.key for q in picked])].sort_values("cost", ascending=False)


def delta_kpi(label, now, before, fmt, better_up=True, sub=""):
    d = now - before
    good = (d >= 0) == better_up
    arrow = "▲" if d >= 0 else "▼"
    return kpi(label, fmt(now), f'<span class="{"up" if good else "down"}">{arrow} {fmt(abs(d))}</span> '
                                f'לעומת {fmt(before)} קודם{(" · " + sub) if sub else ""}')


def trend_section():
    cut = fdf.created.max() - C.TREND_DAYS * 86_400_000
    new, old = fdf[fdf.created > cut], fdf[fdf.created <= cut]
    if len(new) < 20 or len(old) < 20:
        return
    section(f"{C.TREND_DAYS} הימים האחרונים מול התקופה שלפניהם",
            f"{len(new):,} משחקים מאז {fmt_date(cut)}, לעומת {len(old):,} משחקים לפני כן.")
    c = st.columns(3)
    with c[0]:
        md(delta_kpi("אחוז נקודות", new.score.mean(), old.score.mean(), pct))
    with c[1]:
        md(delta_kpi("משחקים עם טעות בפתיחה", new.first_error_ply.notna().mean(), old.first_error_ply.notna().mean(),
                     pct, better_up=False))
    with c[2]:
        md(delta_kpi("מסע הטעות הראשונה (ממוצע)", new.first_error_move.mean(), old.first_error_move.mean(),
                     lambda x: f"{x:.1f}", sub="מאוחר יותר = טוב יותר"))


def page_overview():
    o = overall(fdf)
    has_err = fdf.first_error_ply.notna()
    clean, dirty = fdf[~has_err].score.mean(), fdf[has_err].score.mean()
    c = st.columns(4)
    with c[0]:
        md(kpi("אחוז נקודות", pct(o["score"]), wdl(o["win"], o["draw"], o["loss"])))
    with c[1]:
        md(kpi("משחקים עם טעות בפתיחה", pct(o["games_with_error"] / o["games"]),
               f'{o["games_with_error"]:,} מתוך {o["games"]:,} משחקים היתה לפחות טעות אחת ב‑{C.ANALYZE_PLIES // 2} המסעים הראשונים'))
    with c[2]:
        md(kpi("מתי מגיעה הטעות הראשונה", f'מסע {o["avg_first_error_move"]:.1f}',
               "בממוצע, במשחקים שבהם היתה טעות בפתיחה"))
    with c[3]:
        md(kpi("כמה עולה טעות בפתיחה", f'<span class="ltr" style="font-family:inherit;font-size:1em">{(dirty - clean) * 100:+.0f}%</span>',
               f"{pct(clean)} נקודות במשחקים בלי טעות, לעומת {pct(dirty)} במשחקים עם טעות", "red"))

    if len(colors) == 2:
        section("לבן מול שחור")
        a, b = st.columns(2)
        with a:
            md(color_card("white"))
        with b:
            md(color_card("black"))

    trend_section()
    st.markdown("")
    rec = [p for p in probs if p["count"] >= C.MIN_PROBLEM_GAMES and p["status"] != "learned"]
    if rec:
        with st.container(border=True, key="card_cta"):
            a, b, c2 = st.columns([4, 1.3, 1.3], vertical_alignment="center")
            with a:
                rep = sum(p["status"] == "repeating" for p in rec)
                md(f'<div class="card-h"><span class="t">{you(f"יש {len(rec)} טעויות שחזרת עליהן", f"{len(rec)} טעויות חוזרות של {esc(user)}")} ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר</span></div>'
                   f'<div class="muted small">{you(f"ב‑{rep} מהן טעית שוב גם בפעם האחרונה שהגעת לעמדה. אלה המקומות הכי קלים לתקן.", f"ב‑{rep} מהן הטעות חזרה גם בפעם האחרונה. כדאי להוביל לעמדות האלה.")}</div>')
            b.button("לרשימת הטעויות", on_click=go, args=("mistakes",), width="stretch")
            if me:
                c2.button("להתחיל לתרגל", on_click=go, args=("practice",), type="primary", width="stretch")


    section(you("על מה כדאי לעבוד קודם", f"הפתיחות היקרות ביותר ל‑{esc(user)}"),
            you("הפתיחות שעולות לך הכי הרבה נקודות ביחס לממוצע שלך באותו צבע – שיפור בהן ישפיע הכי מהר על התוצאות.",
                f"הפתיחות שעולות ל‑{esc(user)} הכי הרבה נקודות ביחס לממוצע באותו צבע – לשם כדאי לכוון את המשחק."))
    top = focus_openings(3)
    if top.empty:
        empty(you("אין פתיחה שמורידה את הממוצע שלך. יפה!", "אין פתיחה שמורידה את הממוצע באופן בולט."))
    else:
        cols = st.columns(len(top))
        for i, (col, r) in enumerate(zip(cols, top.itertuples())):
            with col, st.container(border=True, key=f"card_focus_{i}", height="stretch"):
                err = (f'<div class="note">הטעות הנפוצה: <span class="ltr">{esc(r.top_error)}</span> '
                       f'(ב‑{pct(r.top_error_share)} מהמשחקים)</div>') if r.top_error else ""
                md(f'<div class="card-h"><span class="rank">{i + 1}</span>{chip(r.color)}'
                   f'{"<span class=\'badge b-red\'>בעייתית</span>" if r.toxic else ""}</div>'
                   f'<div class="card-h"><span class="t">{en(r.opening)}</span></div>'
                   f'{moves_html(r.group.split())}'
                   f'<div class="stats s3"><div><div class="k">אחוז נקודות</div><div class="v">{pct(r.score)}</div></div>'
                   f'<div><div class="k">נקודות שאבדו</div><div class="v" style="color:var(--red)">{r.cost:.1f}</div></div>'
                   f'<div><div class="k">משחקים</div><div class="v">{r.games}</div></div></div>{err}')
                st.button("לטעויות בפתיחה הזו", key=f"focus_{i}", on_click=go, args=("openings", r.key),
                          icon=":material/arrow_back:", width="stretch")

    a, b = st.columns(2, gap="large")
    with a:
        section("הדירוג לאורך זמן")
        st.altair_chart(chart_rating(), width="stretch")
    with b:
        section("באיזה מסע מגיעה הטעות הראשונה", "מספר המשחקים לפי המסע של הטעות הראשונה")
        st.altair_chart(chart_error_moves(), width="stretch")


# ---------------------------------------------------------------- openings
def board_viewer(r, color, key):
    """Step through a game up to its first error, with arrows at the decision point."""
    moves = r.moves.split()
    err = int(r.first_error_ply)
    k = f"ply_{key}_{r.id}"
    st.session_state.setdefault(k, err - 1)
    ply = st.session_state[k]
    board, last = position_at(moves, ply)
    decision = ply == err - 1
    a, b = st.columns([1.15, 1], gap="large")
    with a:
        st.image(board_svg(board, color, last, [(r.played, RED), (r.best, GREEN)] if decision else
                           [(r.played, RED)] if ply == err else []), width=460)
        n = st.columns(4)
        n[0].button("התחלה", key=f"{k}_s", on_click=set_state, args=(k, 0), disabled=ply == 0, width="stretch")
        n[1].button("הקודם", key=f"{k}_p", on_click=set_state, args=(k, max(0, ply - 1)), disabled=ply == 0, width="stretch")
        n[2].button("הבא", key=f"{k}_n", on_click=set_state, args=(k, min(err, ply + 1)), disabled=ply >= err, width="stretch")
        n[3].button("רגע הטעות", key=f"{k}_e", on_click=set_state, args=(k, err - 1), disabled=decision,
                    type="primary", width="stretch")
    with b:
        best = san_of(r.fen_before, r.best)
        if decision:
            md(f'<div class="card-h"><span class="t">רגע ההחלטה</span><span class="badge b-blue">מסע {(err + 1) // 2}</span></div>'
               f'<div class="cmp"><div class="bad"><div class="k">{you("שיחקת", "שוחק")}</div><div class="v">{esc(r.played_san)}</div></div>'
               f'<div class="good"><div class="k">עדיף</div><div class="v">{esc(best)}</div></div></div>'
               f'<div class="note">סיכויי הניצחון {you("שלך", f"של {esc(user)}")} לפי המנוע: <b>{r.win_before:.0f}%</b> לפני המסע ← <b>{r.win_after:.0f}%</b> אחרי.</div>'
               f'{arrow_legend()}')
        elif ply == err:
            md(f'<div class="card-h"><span class="t">אחרי הטעות</span></div>'
               f'<div class="note">החץ האדום מראה את {you("המסע ששיחקת", "המסע ששוחק")}. לחצו "רגע הטעות" כדי לראות מה היה עדיף.</div>')
        else:
            md(f'<div class="card-h"><span class="t">מהלך המשחק</span></div>'
               f'<div class="note">עברו קדימה עד רגע הטעות, או לחצו "רגע הטעות" כדי לקפוץ ישר אליו.</div>')
        md('<div style="margin-top:14px"></div>' + moves_html(moves[:err], upto=err, cur=ply if ply < err else None, err=err))
        md(f'<div class="note" style="margin-top:12px">{RESULTS[r.result]} · {fmt_date(r.created)} · '
           f'<a href="https://lichess.org/{r.id}/{color}#{err}" target="_blank">פתיחת המשחק ב־Lichess ↗</a></div>')


def short_name(r):
    """In tree view a child repeats its parent's name ("Vienna Game: Vienna Gambit" under "Vienna Game"): drop it."""
    par = tbl[(tbl.color == r.color) & (tbl.group == r.parent)]
    pn = par.opening.iat[0] if len(par) else ""
    if pn and r.opening.startswith(pn + ": "):
        return r.opening[len(pn) + 2:]
    if pn and r.opening == pn:  # same name: show the moves this branch adds instead
        k = int(par.plies.iat[0])
        return " ".join(move_label(i, m) if i % 2 or i == k + 1 else m
                        for i, m in enumerate(r.group.split()[k:], k + 1))
    return r.opening


def page_openings():
    section(you("עץ הפתיחות שלך", f"עץ הפתיחות של {esc(user)}"),
            f"כל רצף ששוחק לפחות {C.MIN_GROUP_GAMES} פעמים. כל שורה כוללת גם את ההמשכים שלה (המוזחים מתחתיה). "
            "בחרו שורה כדי לראות את הטעויות בה על הלוח.")
    if tbl.empty:
        empty("אין פתיחה ששוחקה מספיק פעמים בסינון הנוכחי.")
        return
    a, b, _ = st.columns([1.4, 1.4, 2])
    show = a.segmented_control("הצג", ["all", "toxic"], default="all", key="op_show",
                               format_func={"all": "כל הפתיחות", "toxic": f"רק בעייתיות ({int(tbl.toxic.sum())})"}.get)
    sort = b.selectbox("סדר", ["order", "diff", "cost", "score", "games"], key="op_sort",
                       format_func={"order": "לפי העץ", "diff": "מול הממוצע בצבע (החלשות קודם)",
                                    "cost": "הכי הרבה נקודות שאבדו", "score": "אחוז נקודות נמוך",
                                    "games": "הכי הרבה משחקים"}.get)
    t = tbl[tbl.toxic] if show == "toxic" else tbl
    t = t.sort_values(sort, ascending=sort in ("order", "score", "diff")).reset_index(drop=True)
    if t.empty:
        empty("אין פתיחות בעייתיות בסינון הנוכחי.")
        return
    tree = sort == "order" and show == "all"
    # the table is right-aligned, so the tree indent goes after the (left-to-right) name: deeper rows shift left
    view = pd.DataFrame({
        **({"צבע": t.color.map(COLORS)} if len(colors) == 2 else {}),
        # the column holds ~30 characters; deeper rows lose room to the indent, so their names are shortened more
        "פתיחה": [clip(short_name(r), max(14, 28 - 2 * r.depth)) + ("  ⚠" if r.toxic else "")
                  + (" ┘" + " " * r.depth if r.depth else "")
                  for r in t.itertuples()] if tree else [clip(o, 28) + ("  ⚠" if x else "") for x, o in zip(t.toxic, t.opening)],
        "מסעים": [LRM + tail_moves(g) + LRM for g in t.group], "משחקים": t.games,
        "אחוז נקודות": t.score * 100, "מול הממוצע": (t.score - t.base) * 100, "נקודות שאבדו": t.cost})
    key = f"op_table_{show}_{sort}_{st.session_state.get('op_nonce', 0)}"
    ev = rtl_table(view, on_select="rerun", selection_mode="single-row", key=key, height=min(38 + 35 * len(view), 460),
                   column_config={
                       "צבע": st.column_config.TextColumn(width=50, alignment="right"),
                       "פתיחה": st.column_config.TextColumn(width=235, alignment="right", help="⚠ = פתיחה בעייתית (ראו הסבר בסרגל הצד)"),
                       "מסעים": st.column_config.TextColumn(width=175, alignment="left"),
                       "משחקים": st.column_config.NumberColumn(width=60, help="כולל כל ההמשכים של הרצף"),
                       "אחוז נקודות": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%", width=105),
                       "מול הממוצע": st.column_config.NumberColumn(format="%+.0f%%", width=80, help=you("לעומת הממוצע שלך באותו צבע", "לעומת הממוצע של השחקן באותו צבע")),
                       "נקודות שאבדו": st.column_config.NumberColumn(format="%.1f", width=85, help="משחקים × (הממוצע באותו צבע − אחוז הנקודות בפתיחה)")})
    if ev.selection.rows:
        st.session_state.op_key = t.key.iat[ev.selection.rows[0]]
    sel = st.session_state.get("op_key")
    if sel not in set(tbl.key):  # first visit: the line that costs the most points (as on the overview)
        top = focus_openings(1)
        sel = top.key.iat[0] if len(top) else t.key.iat[0]
    op = tbl[tbl.key == sel].iloc[0]
    opening_detail(op)


def opening_detail(op):
    color = op.color
    scope = node_games(op)
    diff = (op.score - op.base) * 100
    eco = f'<span class="badge b-gray">{esc(op.eco)}</span>' if op.eco else ""
    toxic = '<span class="badge b-red">⚠ בעייתית</span>' if op.toxic else ""
    with st.container(border=True, key="card_opening"):
        md(f'<div class="card-h">{chip(color)}<span class="t" style="font-size:1.3rem">{en(op.opening)}</span>{eco}{toxic}</div>'
           f'{moves_html(op.group.split())}'
           f'<div class="stats"><div><div class="k">משחקים</div><div class="v">{op.games}</div></div>'
           f'<div><div class="k">אחוז נקודות</div><div class="v">{pct(op.score)}</div></div>'
           f'<div><div class="k">מול הממוצע {you("שלך", f"של {esc(user)}")} ב{COLORS[color]}</div><div class="v" style="color:{"var(--green)" if diff >= 0 else "var(--red)"}"><span dir="ltr">{diff:+.0f}%</span></div></div>'
           f'<div><div class="k">טעות עד מסע {C.EARLY_ERROR_MOVE}</div><div class="v">{pct(op.early_error_share)}</div></div></div>'
           f'{wdl(op.win, op.draw, op.loss)}')

        # navigate the tree: parent and children of this node
        kids = tbl[(tbl.color == color) & (tbl.parent == op.group)].sort_values("games", ascending=False)
        parent = tbl[(tbl.color == color) & (tbl.group == op.parent)] if op.parent else tbl.iloc[0:0]
        items = [(f"↑ {LRM}{clip(parent.opening.iat[0], 22)}{LRM}", parent.key.iat[0])] if len(parent) else []
        items += [(f"{LRM}{clip(short_name(k), 22)}{LRM} · {k.games} · {pct(k.score)}", k.key)
                  for k in kids.head(7).itertuples()]
        if items:
            md('<div class="note" style="margin:14px 0 4px"><b>המשכים בעץ</b></div>')
            cols = st.columns(min(4, len(items)))
            for j, (label, k) in enumerate(items):
                cols[j % len(cols)].button(label, key=f"nav_{op.key}_{j}", on_click=go, args=("openings", k),
                                           width="stretch", help=tbl.loc[tbl.key == k, "line"].iat[0])

        # first error per game after this node's own moves
        e = all_errors[all_errors.id.isin(scope.id) & (all_errors.ply > op.plies)].sort_values("ply").drop_duplicates("id")
        errs = e.rename(columns={"ply": "first_error_ply"}).merge(scope[["id", "moves", "result", "created"]], on="id")
        info = {(p["color"], p["key"], p["played"]): p for p in probs}
        errs["info"] = [info.get((color, k, m)) for k, m in zip(errs.key, errs.played_san)]
        hide = st.toggle(you("הסתר טעויות שכבר למדתי", "הסתר טעויות שנלמדו"), True, key="op_hide")
        if hide:
            errs = errs[[not (i and i["status"] == "learned") for i in errs["info"]]] if len(errs) else errs
        errs = errs.sort_values("drop", ascending=False).reset_index(drop=True)
        if not analyzed:
            md('<div class="sec" style="margin-top:1.2rem"><h3>הטעויות בפתיחה הזו</h3></div>')
            empty("הטעויות עוד לא נותחו במנוע. אפשר להפעיל את הניתוח בסרגל הצד.")
            return
        md(f'<div class="sec" style="margin-top:1.2rem"><h3>הטעויות בפתיחה הזו ({len(errs)})</h3>'
           f'<p>הטעות הראשונה בכל משחק אחרי רצף הפתיחה, מהיקרה לזולה. בחרו טעות כדי לראות אותה על הלוח.</p></div>')
        if errs.empty:
            empty("אין טעויות פתוחות בפתיחה הזו.")
            return
        ev = rtl_table(pd.DataFrame({
            you("המסע שלך", "המסע ששוחק"): [LRM + move_label(int(p), s) + LRM for p, s in zip(errs.first_error_ply, errs.played_san)],
            "עדיף": [LRM + (san_of(f, b) or "") + LRM for f, b in zip(errs.fen_before, errs.best)],
            "סיכויי ניצחון": [f"{a:.0f}% ← {b:.0f}%" for a, b in zip(errs.win_before, errs.win_after)],
            "חזרת על הטעות": [f"{i['mistakes']} מתוך {i['reached']}" if i else "—" for i in errs["info"]],
            "מצב": [STATUS[i["status"]][0] if i else "—" for i in errs["info"]],
            "תוצאה": errs.result.map(RESULTS), "תאריך": errs.created.map(fmt_date)}),
            on_select="rerun", selection_mode="single-row",
            key=f"errs_{op.key}_{hide}", height=min(38 + 35 * len(errs), 250),
            column_config={"סיכויי ניצחון": st.column_config.TextColumn(
                alignment="right", help="סיכויי הניצחון לפי המנוע: לפני המסע ← אחריו")})
        r = errs.iloc[ev.selection.rows[0] if ev.selection.rows else 0]
        st.markdown("")
        board_viewer(r, color, op.key)


# ---------------------------------------------------------------- mistakes
def usual_html(p):
    """What the user usually plays in this position (all visits, not only the mistakes)."""
    moves = " · ".join(f'<span class="ltr">{esc(m)}</span> ×{c}' for m, c in list(p["moves"].items())[:4])
    if p["usual"] is None:
        head = f'{you("אין לך מסע קבוע כאן", "אין מסע קבוע בעמדה הזו")}: כמה מסעים שוחקו אותו מספר פעמים.'
    elif p["usual"] == p["played"]:
        head = f'<b>{you("זה המסע הקבוע שלך כאן", "זה המסע הקבוע בעמדה הזו")}</b> ({p["usual_n"]} מתוך {p["reached"]} פעמים).'
    else:
        head = (f'{you("בדרך כלל אתה משחק כאן", "המסע הרגיל בעמדה הוא")} <span class="ltr">{esc(p["usual"])}</span> '
                f'({p["usual_n"]} מתוך {p["reached"]}), והטעות היא סטייה.')
    return f'{head} כל המסעים בעמדה: {moves}'


def replies_html(p, punish_first):
    rows = "".join(
        f'<tr><td><span class="ltr">{esc(move_label(p["ply"] + 1, r["san"]))}</span>'
        f'{" <span class=\'badge b-red\'>העונש</span>" if r["san"] == punish_first else ""}</td>'
        f'<td>{r["n"]}</td><td>{pct(r["score"])}</td></tr>' for r in p["replies"][:4])
    return (f'<div class="note" style="margin-top:10px"><b>מה היריבים ענו בפועל</b></div>'
            f'<table class="replies"><tr><th>תשובה</th><th>משחקים</th><th>{you("הציון שלך", "ציון")}</th></tr>{rows}</table>')


def cost_note(p):
    base = f'{pct(p["score"])} ב‑{p["count"]} משחקים מול ממוצע של {pct(p["avg"])} בצבע'
    if p["cost"] < -0.05:
        return (f"המנוע מחשיב את זה טעות, אבל בפועל המשחקים האלה הלכו טוב מהממוצע ({base}): "
                "כנראה היריבים לא ניצלו אותה. מול יריב שיודע את הקו זה עלול לעלות ביוקר.")
    return f"מחיר בנקודות = כמה נקודות ירדו במשחקים האלה לעומת הממוצע: {base}."


def line_html(sans, first_ply, cur):
    """Numbered line with the move currently on the board highlighted (cur = number of moves played, 0 = none)."""
    out = []
    for i, san in enumerate(sans, 1):
        ply = first_ply + i - 1
        num = f'<span class="n">{(ply + 1) // 2}.</span>' if ply % 2 else (f'<span class="n">{(ply + 1) // 2}...</span>' if i == 1 else "")
        cls = "cur" if i == cur else "dim" if i > cur else ""
        out.append(f'<span class="u">{num}<span class="m {cls}">{esc(san)}</span></span> ')
    return f'<div class="moves">{"".join(out)}</div>'


def line_board(p, x):
    """The card's board: the mistake with arrows, or the correct line / the punishment played out move by move."""
    k = f'lb_{abs(hash((p["color"], p["key"], p["played"])))}'
    mode = st.segmented_control("על הלוח", ["mistake", "better", "punish"], default="mistake", key=f"{k}_mode",
                                format_func={"mistake": "הטעות", "better": "הקו הנכון", "punish": "קו העונש"}.get,
                                label_visibility="collapsed", width="stretch")
    before = chess.Board(p["fen"])
    if mode not in ("better", "punish"):
        st.image(board_svg(before, p["color"], None, [(p["played_uci"], RED), (p["best_uci"], GREEN)], size=400), width=400)
        md(arrow_legend())
        return
    if mode == "better":
        start, sans, first_ply = before, x.get("better_sans") or [], p["ply"]
    else:
        start = before.copy()
        start.push(chess.Move.from_uci(p["played_uci"]))
        sans, first_ply = x.get("punish_sans") or [], p["ply"] + 1
    if not sans:
        st.caption("אין קו להצגה בעמדה הזו.")
        return
    pk = f"{k}_{mode}_ply"
    st.session_state.setdefault(pk, 1)
    cur = min(st.session_state[pk], len(sans))
    b, last = start.copy(), None
    for san in sans[:cur]:
        last = b.push_san(san)
    st.image(board_svg(b, p["color"], last, size=400), width=400)
    c = st.columns(4)
    c[0].button("התחלה", key=f"{pk}_s", on_click=set_state, args=(pk, 0), disabled=cur == 0, width="stretch")
    c[1].button("הקודם", key=f"{pk}_p", on_click=set_state, args=(pk, max(0, cur - 1)), disabled=cur == 0, width="stretch")
    c[2].button("הבא", key=f"{pk}_n", on_click=set_state, args=(pk, min(len(sans), cur + 1)),
                disabled=cur >= len(sans), width="stretch")
    c[3].button("סוף", key=f"{pk}_e", on_click=set_state, args=(pk, len(sans)), disabled=cur >= len(sans), width="stretch")
    intro = ("הקו של המנוע אחרי המסע הנכון:" if mode == "better"
             else f'מה קורה אחרי {move_label(p["ply"], p["played"])}, לפי המנוע:')
    md(f'<div class="note" style="margin-top:6px">{intro}</div>' + line_html(sans, first_ply, cur))


def mistake_card(p, n):
    x = explain_p(p)
    lv = level_view(p)
    works = bool(lv and lv.get("works"))
    with st.container(border=True, key=f"card_mk_{n}"):
        a, b = st.columns([1, 1.35], gap="large")
        with a:
            line_board(p, x)
            md(f'<div class="note" style="margin-top:10px"><a href="{x["url"]}" target="_blank">פתיחת העמדה בלוח הניתוח של Lichess ↗</a></div>')
            if me:
                st.button("התאמן על הקו הזה", key=f"train_{tr_key(p)}", on_click=start_training, args=(tr_key(p),),
                          icon=":material/school:", width="stretch", type="primary")
        with b:
            _, _, why = STATUS[p["status"]]
            cost = p["cost"]
            cost_txt = (f'<span style="color:var(--red)">−{cost:.1f}</span>' if cost > 0.05 else
                        f'<span style="color:var(--green)">+{-cost:.1f}</span>' if cost < -0.05 else "0")
            level_badge = f'<span class="badge b-blue">עובד ברמה {you("שלך", "הזו")}</span>' if works else ""
            md(f'<div class="card-h"><span class="rank">#{n}</span>{chip(p["color"])}{badge(p["status"])}{level_badge}</div>'
               f'<div class="card-h"><span class="t">{en(p["opening"])}</span></div>'
               f'{moves_html(p["pre_moves"])}'
               f'<div class="cmp"><div class="bad"><div class="k">{you("שיחקת", "שוחק")}</div><div class="v">{esc(move_label(p["ply"], p["played"]))}</div></div>'
               f'<div class="good"><div class="k">עדיף לשחק</div><div class="v">{esc(move_label(p["ply"], p["best_san"] or "?"))}</div></div></div>'
               f'<div class="why"><b>{"למה Stockfish מחשיב את זה טעות" if works else "למה זו טעות"}:</b> {esc(x["why"])}</div>'
               f'{level_html(p, lv)}'
               f'<div class="lines"><span class="k">העונש (מנוע):</span><span class="ltr">{esc(x["punish"]) or "—"}</span>'
               f'<span class="k">הקו הנכון:</span><span class="ltr">{esc(x["better"]) or "—"}</span></div>'
               f'<div class="stats"><div><div class="k">{you("חזרת על הטעות", "חזרות על הטעות")}</div><div class="v">{p["mistakes"]} מתוך {p["reached"]}</div></div>'
               f'<div><div class="k">סיכויי ניצחון</div><div class="v">{p["win_before"]:.0f}% ← {p["win_after"]:.0f}%</div></div>'
               f'<div><div class="k">{"מחיר בנקודות" if cost > 0.05 else "בפועל: רווח בנקודות" if cost < -0.05 else "מחיר בנקודות"}</div><div class="v"><span dir="ltr">{cost_txt}</span></div></div>'
               f'<div><div class="k">פעם אחרונה</div><div class="v">{fmt_date(p["last_mistake"]) if p["last_mistake"] else "—"}</div></div></div>'
               f'<div class="note">{cost_note(p)}</div>'
               f'{replies_html(p, x["punish_first"])}'
               f'<div class="note" style="margin-top:10px">{usual_html(p)}</div>'
               f'<div class="note">{why}</div>'
               f'<div class="note" style="margin-top:10px">המשחקים:</div>{game_links(p["games"], p["color"], p["ply"])}')
            if lv and lv.get("ex"):
                md(explorer_html(lv["ex"], p["color"]))
            elif lv:
                st.caption(f"Opening Explorer לא זמין כרגע: {lv['error']}.")


LEVEL_MIN_GAMES = 100   # fewer Lichess games than this for the move played: no verdict


def level_range(rating):
    b = [int(x) for x in similar_ratings(rating).split(",")]
    return f"{b[0]}–{b[-1] + 200}"


def level_view(p):
    """How the move played and the engine's move score in Lichess games at the player's rating (Opening Explorer).
    works = the move played is common enough and scores at least 50% and at least as well as the engine's move."""
    if not C.lichess_token():
        return None
    rating = int(fdf[fdf.color == p["color"]].rating.median())
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


def sig_items(items):
    return hash(tuple((p["key"], p["played"]) for p in items))


def recurring(items):
    """Practice and focus use only mistakes that really repeat (3+ games); 2+ when there are none."""
    rec = [p for p in items if p["count"] >= C.MIN_PROBLEM_GAMES]
    return rec or [p for p in items if p["count"] >= 2]


def page_mistakes():
    if not analyzed:
        section("טעויות שחוזרות על עצמן")
        empty(f"הטעויות של {esc(user)} עוד לא נותחו במנוע. "
              "הפעילו את הניתוח בסרגל הצד (\"נתח טעויות ב־Stockfish\"); בינתיים מסך נקודות החולשה כבר מוכן.")
        return
    rec = [p for p in probs if p["count"] >= C.MIN_PROBLEM_GAMES]
    counts = {s: sum(p["status"] == s for p in rec) for s in STATUS}
    section("טעויות שחוזרות על עצמן",
            you(f"עמדות שבהן שיחקת את אותו מסע שגוי ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר. לכל טעות: איך הגעת לעמדה, "
                "מה שיחקת, מה עדיף, מה אתה משחק שם בדרך כלל, והאם הפסקת לחזור עליה.",
                f"עמדות שבהן אותו מסע שגוי של {esc(user)} חזר ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר: איך מגיעים לעמדה, "
                "מה שוחק, מה עדיף, מה המסע הרגיל שם, והאם הטעות עדיין חוזרת. שימושי להכנה לקראת משחק."))
    c = st.columns(4)
    c[0].markdown(kpi("טעויות חוזרות", len(rec), f"אותו מסע שגוי ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר"), unsafe_allow_html=True)
    c[1].markdown(kpi("עדיין חוזרות", counts["repeating"], STATUS["repeating"][2], "red"), unsafe_allow_html=True)
    c[2].markdown(kpi("בדרך לתיקון", counts["improving"], STATUS["improving"][2]), unsafe_allow_html=True)
    c[3].markdown(kpi("נלמדו", counts["learned"], STATUS["learned"][2], "green"), unsafe_allow_html=True)

    st.markdown("")
    a, b, c3 = st.columns([1.6, 1.4, 1.2], vertical_alignment="bottom")
    n2 = sum(p["count"] >= 2 for p in probs)
    scope = a.segmented_control("אילו טעויות", ["rec", "two", "all"], default="rec", key="mk_scope",
                                format_func={"rec": f"{C.MIN_PROBLEM_GAMES}+ משחקים ({len(rec)})", "two": f"2+ ({n2})",
                                             "all": f"כולן ({len(probs)})"}.get)
    sort = b.selectbox("מיון", ["default", "count", "avg_drop", "total_drop"], key="mk_sort",
                       format_func={"default": "מומלץ (חוזרות ויקרות קודם)", "count": "הכי הרבה חזרות",
                                    "avg_drop": "הטעות הכי חמורה", "total_drop": "הכי הרבה הפסד מצטבר"}.get)
    hide = c3.toggle("הסתר טעויות שנלמדו", True, key="mk_hide")
    items = {"all": probs, "two": [p for p in probs if p["count"] >= 2]}.get(scope, rec)
    items = sorted((p for p in items if not (hide and p["status"] == "learned")), key=SORTS[sort])
    if C.lichess_token() and items:
        # checked only for repeated mistakes, to keep the number of Explorer requests small
        practical = [p for p in items if p["count"] >= 2 and (level_view(p) or {}).get("works")]
        if practical and st.toggle(f"הסתר מסעים שעובדים ברמה {you('שלי', 'של השחקן')} ({len(practical)})", False,
                                   key="mk_hide_level",
                                   help="מסעים ש־Stockfish מחשיב טעות, אבל ב־Lichess, ברמת דירוג דומה, הם נפוצים "
                                        "ומשיגים לפחות 50% ולפחות כמו המסע של המנוע (למשל גמביטים מעשיים)."):
            skip = {(q["key"], q["played"]) for q in practical}
            items = [p for p in items if (p["key"], p["played"]) not in skip]
    if not items:
        if probs and scope != "all":
            empty(f"אין טעויות שחוזרות {'ב‑' + str(C.MIN_PROBLEM_GAMES) + '+' if scope == 'rec' else 'ב‑2+'} משחקים בסף הנוכחי "
                  f"({thr}%). יש {len(probs)} טעויות בסך הכל – בחרו \"כולן\" למעלה, או הורידו את הסף בסרגל הצד.")
        elif probs:
            empty("כל הטעויות בסף הזה סומנו כנלמדו. אפשר לבטל את \"הסתר טעויות שנלמדו\".")
        else:
            empty("אין טעויות בסף הנוכחי. 🎉")
        return
    export = items[:60]
    a, b = st.columns([3, 1.3], vertical_alignment="center")
    a.caption(f"ייצוא {len(export)} העמדות הראשונות כ־PGN ל־Lichess Study (Study ← Add chapter ← PGN). בכל פרק: הקו של המנוע, "
              "המסע ששוחק עם ההסבר וקו העונש, ותשובות היריבים בפועל כווריאציות.")
    pgn_key = f"pgn_{user}_{thr}_{sig_items(export)}"
    if pgn_key in st.session_state:
        b.download_button("הורדת קובץ PGN", st.session_state[pgn_key], file_name=f"opening-mistakes-{user}.pgn",
                          mime="application/x-chess-pgn", icon=":material/download:", width="stretch", type="primary")
    elif b.button(f"הכנת PGN ({len(export)} עמדות)", icon=":material/description:", width="stretch"):
        with st.spinner("מחשב קווים במנוע לכל עמדה..."):
            st.session_state[pgn_key] = study_pgn(export)
        st.rerun()
    if not C.lichess_token():
        st.caption("כדי לראות גם מה משחקים שחקנים ברמה דומה בכל עמדה (Lichess Opening Explorer) צריך טוקן אישי של Lichess בקובץ data/lichess_token.txt: "
                   "ה־API של ה־Explorer דורש כיום טוקן אישי. ראו README.")
    sig = f"{scope}|{sort}|{hide}|{colors}"
    if st.session_state.get("mk_sig") != sig:
        st.session_state.update(mk_sig=sig, mk_n=5)
    for n, p in enumerate(items[: st.session_state.mk_n], 1):
        mistake_card(p, n)
    if st.session_state.mk_n < len(items):
        st.button(f"הצג עוד ({len(items) - st.session_state.mk_n} נוספות)", width="stretch",
                  on_click=set_state, args=("mk_n", st.session_state.mk_n + 5))

    with st.expander(f"כל {len(items)} הטעויות בטבלה אחת"):
        rtl_table(pd.DataFrame({
            "צבע": [COLORS[p["color"]] for p in items], "פתיחה": [p["opening"] for p in items],
            you("שיחקת", "שוחק"): [LRM + move_label(p["ply"], p["played"]) + LRM for p in items],
            "עדיף": [LRM + move_label(p["ply"], p["best_san"] or "?") + LRM for p in items],
            "ביקורים בעמדה": [p["reached"] for p in items], "טעויות": [p["mistakes"] for p in items],
            "שיעור טעות": [p["rate"] * 100 for p in items], "מצב": [STATUS[p["status"]][0] for p in items],
            "בדרך כלל": [LRM + (p["usual"] or "—") + LRM for p in items],
            "ירידה בסיכויים": [p["avg_drop"] for p in items], "פעם אחרונה": [p["last_mistake"] for p in items]}),
            column_config={"שיעור טעות": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
                           "בדרך כלל": st.column_config.TextColumn(alignment="right", help="המסע ששוחק הכי הרבה בעמדה הזו"),
                           "ירידה בסיכויים": st.column_config.NumberColumn(format="%.0f%%", help="ממוצע הירידה בסיכויי הניצחון")})


# ---------------------------------------------------------------- line trainer
TR_REASON = {
    "critical": lambda i: f"רגע קריטי: יש כאן רק מסע אחד טוב (הפער לשני הטוב ביותר: {i['gap']:.0f}% בסיכויי הניצחון).",
    "known": lambda i: ("עדיין תיאוריה מעשית: " + " · ".join(
        x for x in [f"{i['level_n']:,} משחקים ברמה שלך" if i["level_n"] else "",
                    f"{i['masters_n']:,} משחקי מאסטרים" if i["masters_n"] else ""] if x) + "."),
    "default": lambda i: "שלושת המסעים הראשונים תמיד נכללים (אין כאן רגע קריטי וגם לא תיאוריה ידועה).",
    "quiet": lambda i: "העמדה כבר סלחנית ולא נפוצה. עוד מסע אחד לבדיקה, ואם גם הוא כזה, הקו נגמר.",
}
TR_STOP = {
    "quiet": "מכאן העמדה סלחנית: כמה מסעים טובים כמעט באותה מידה, והיא כבר לא נפוצה ברמה שלך או אצל מאסטרים. "
             "אין צורך לשנן הלאה.",
    "max": f"הגענו לתקרה של {C.TRAIN_MAX_MOVES} מסעים.",
    "over": "המשחק הסתיים.",
}


@st.cache_data(show_spinner="המנוע בודק את העמדה...")
def tr_node(fen, color, rating):
    from chessapp.trainer import node
    return node(chess.Board(fen), color, rating)


@st.cache_data(show_spinner="מחפש תגובות של היריב...")
def tr_opp(fen, rating, from_games):
    from chessapp.trainer import opponent_options
    return opponent_options(chess.Board(fen), rating, [dict(san=s, n=n) for s, n in from_games])


def tr_key(p):
    return f'{p["color"]}|{p["key"]}|{p["played"]}'


def start_training(key):
    go("practice")
    st.session_state.pr_mode = "line"
    st.session_state.tr_pick = key


def tr_reset(key, mine_first, p):
    st.session_state.update(tr_sig=(key, mine_first), tr_moves=[], tr_turn="me", tr_done=0, tr_quiet=0, tr_log=[],
                            tr_answer=None, tr_decided=-1, tr_reason=None, tr_stop=None, tr_snaps=[])
    if mine_first:  # train the line that follows the player's own move (it works at the player's level)
        st.session_state.update(tr_moves=[p["played_uci"]], tr_turn="opp", tr_done=1,
                                tr_log=[dict(san=p["played"], ok=True, drop=0, reason="mine", best=p["played"], chosen=p["played"])])


def tr_answer(board, info, uci, color):
    from chessapp.trainer import evaluate
    st.session_state.tr_answer = evaluate(board, info, uci, color)


def tr_continue(board):
    a = st.session_state.tr_answer
    move = a["uci"] if a["ok"] else a["best"]
    san = lambda u: board.san(chess.Move.from_uci(u))
    st.session_state.tr_log.append(dict(san=san(move), chosen=san(a["uci"]), best=san(a["best"]), ok=a["ok"],
                                        drop=a["drop"], is_best=a["is_best"], reason=st.session_state.tr_reason))
    st.session_state.tr_moves.append(move)
    st.session_state.update(tr_done=st.session_state.tr_done + 1, tr_turn="opp", tr_answer=None)


def tr_opp_pick(uci):
    snap = {k: (list(v) if isinstance(v, list) else v) for k, v in st.session_state.items()
            if k in ("tr_moves", "tr_done", "tr_quiet", "tr_log", "tr_decided")}
    st.session_state.tr_snaps.append(snap)
    st.session_state.tr_moves.append(uci)
    st.session_state.tr_turn = "me"


def tr_back():
    snap = st.session_state.tr_snaps.pop()
    st.session_state.update(**snap, tr_turn="opp", tr_answer=None, tr_stop=None)


def page_trainer(items):
    from chessapp.trainer import decide, my_options
    section("אימון קו", "מתקנים את הטעות וממשיכים לשחק את הקו: אחרי כל מסע שלך בוחרים איך היריב עונה, ומוצאים את התשובה הטובה. "
                        "האורך לא קבוע: הקו נמשך כל עוד יש רגעים קריטיים או שהעמדה עדיין נפוצה ברמה שלך או אצל מאסטרים.")
    if not C.lichess_token():
        st.caption("בלי טוקן של Lichess האימון עובד רק לפי המנוע (בלי \"נפוץ ברמה שלך\" ובלי מסד המאסטרים).")
    names = {tr_key(p): f'{COLORS[p["color"]]} · {p["opening"]} · {move_label(p["ply"], p["played"])}' for p in items}
    if st.session_state.get("tr_pick") not in names:
        st.session_state.tr_pick = next(iter(names))
    key = st.selectbox("מאיזו טעות להתחיל?", list(names), format_func=names.get, key="tr_pick")
    p = next(q for q in items if tr_key(q) == key)
    lv = level_view(p)
    mine_first = False
    if lv and lv.get("works"):
        mine_first = st.radio("מה לתרגל?", [False, True], horizontal=True, key=f"tr_variant_{key}",
                              format_func={False: f"הקו של המנוע ({p['best_san']})",
                                           True: f"המסע שלי ({p['played']}) והמשכו – הוא עובד ברמה שלי"}.get)
    if st.session_state.get("tr_sig") != (key, mine_first):
        tr_reset(key, mine_first, p)

    color = p["color"]
    rating = int(fdf[fdf.color == color].rating.median())
    board = chess.Board(p["fen"])
    sans = []
    for u in st.session_state.tr_moves:
        m = chess.Move.from_uci(u)
        sans.append(board.san(m))
        board.push(m)
    last = board.move_stack[-1] if board.move_stack else None
    turn = st.session_state.tr_turn

    info = None
    if turn == "me":
        info = tr_node(board.fen(), color, rating)
        if st.session_state.tr_decided != len(st.session_state.tr_moves):
            go_on, quiet, reason = decide(st.session_state.tr_done, st.session_state.tr_quiet, info, board)
            st.session_state.update(tr_decided=len(st.session_state.tr_moves), tr_quiet=quiet, tr_reason=reason)
            if not go_on:
                st.session_state.update(tr_turn="done", tr_stop=reason)
                turn = "done"

    with st.container(border=True, key="card_trainer"):
        a, b = st.columns([1.15, 1], gap="large")
        ans = st.session_state.tr_answer
        with a:
            arrows = []
            if turn == "me" and ans:
                arrows = [(ans["uci"], GREEN if ans["ok"] else RED)] + ([] if ans["is_best"] else [(ans["best"], GREEN)])
            st.image(board_svg(board, color, last, arrows), width=460)
            md(f'<div class="note">{chip(color)} {en(p["opening"])}</div>' + (line_html(sans, p["ply"], len(sans)) if sans else ""))
        with b:
            done = st.session_state.tr_done
            if turn == "me":
                md(f'<div class="card-h"><span class="t" style="font-size:1.15rem">מסע {done + 1}: תור ה{COLORS[color]}. מה הכי טוב?</span></div>'
                   f'<div class="level">{esc(TR_REASON[st.session_state.tr_reason](info))}</div>')
                if not ans:
                    mistake = p["played_uci"] if not st.session_state.tr_moves else None
                    opts = my_options(board, info, mistake)
                    g = st.columns(2)
                    for j, u in enumerate(opts):
                        g[j % 2].button(board.san(chess.Move.from_uci(u)), key=f"tro_{len(sans)}_{j}_{u}",
                                        on_click=tr_answer, args=(board, info, u, color), width="stretch")
                else:
                    chosen = board.san(chess.Move.from_uci(ans["uci"]))
                    best = board.san(chess.Move.from_uci(ans["best"]))
                    if ans["is_best"]:
                        st.success(f"נכון! {chosen} הוא המסע הטוב ביותר.", icon=":material/check_circle:")
                    elif ans["ok"]:
                        st.success(f"גם טוב: {chosen} רק {ans['drop']:.0f}% פחות מ־{best}. ממשיכים עם המסע שלך.",
                                   icon=":material/check_circle:")
                    else:
                        st.error(f"{chosen} מוריד את סיכויי הניצחון ב־{ans['drop']:.0f}%. הטוב ביותר: {best}. "
                                 f"ממשיכים עם {best}.", icon=":material/cancel:")
                    st.button("המשך", type="primary", on_click=tr_continue, args=(board,), width="stretch",
                              icon=":material/arrow_back:")
            elif turn == "opp":
                from_games = tuple((r["san"], r["n"]) for r in p["replies"]) if mine_first and len(sans) == 1 else ()
                opts = tr_opp(board.fen(), rating, from_games)
                if not opts:
                    st.session_state.update(tr_turn="done", tr_stop="over")
                    st.rerun()
                md(f'<div class="card-h"><span class="t" style="font-size:1.15rem">תור היריב: איך הוא עונה?</span></div>'
                   '<div class="note">בחרו תגובה. אחר כך אפשר לחזור ולנסות תגובה אחרת.</div>')
                for j, o in enumerate(opts):
                    st.button(f'{o["san"]}   ·   {" · ".join(o["tags"])}', key=f"tropp_{len(sans)}_{o['uci']}",
                              on_click=tr_opp_pick, args=(o["uci"],), width="stretch")
            else:
                log = st.session_state.tr_log
                own = [l for l in log if l.get("reason") != "mine"]
                ok = sum(l["ok"] for l in own)
                why_asked = {"critical": "רגע קריטי", "known": "תיאוריה", "default": "ברירת מחדל", "quiet": "סלחני"}
                rows = "".join(
                    f'<tr><td>{"✓" if l["ok"] else "✗"}</td><td><span class="ltr">{esc(l["chosen"])}</span></td>'
                    f'<td>{"" if l["ok"] else en(l["best"])}</td>'
                    f'<td class="muted small">{why_asked.get(l["reason"], "")}</td></tr>' for l in own)
                md(f'<div class="card-h"><span class="t" style="font-size:1.15rem">סוף הקו: {ok} מתוך {len(own)} נכונים</span></div>'
                   f'<div class="level">{TR_STOP.get(st.session_state.tr_stop, "")}</div>'
                   f'<table class="replies"><tr><th></th><th>בחרת</th><th>הטוב ביותר</th><th>למה נשאל</th></tr>{rows}</table>')
                c1, c2 = st.columns(2)
                if st.session_state.tr_snaps:
                    c1.button("תגובה אחרת של היריב", on_click=tr_back, width="stretch", icon=":material/alt_route:")
                c2.button("מההתחלה", on_click=tr_reset, args=(key, mine_first, p), width="stretch", icon=":material/replay:")


# ---------------------------------------------------------------- practice
def answer(choice, best):
    st.session_state.pr_answer = choice
    st.session_state.pr_n += 1
    st.session_state.pr_ok += int(choice == best)


def next_q():
    st.session_state.pr_i += 1
    st.session_state.pr_answer = None


def page_practice():
    mode = st.segmented_control("סוג תרגול", ["line", "quiz"], default="line", key="pr_mode",
                                format_func={"line": "אימון קו (מתקנים וממשיכים לשחק)", "quiz": "חידון מהיר (מסע אחד)"}.get,
                                label_visibility="collapsed")
    if mode != "quiz":
        items = sorted(recurring([p for p in probs if p["status"] != "learned"]), key=SORTS["default"])
        if not items:
            empty("אין כרגע טעויות חוזרות לאמן עליהן. 🎉")
            return
        page_trainer(items)
        return
    section("תרגול", "העמדות שבהן טעית. מצאו את המסע הטוב ביותר – כמו במשחק אמיתי.")
    sources = {"mistakes": f"הטעויות החוזרות שלי ({C.MIN_PROBLEM_GAMES}+ משחקים)"}
    if not tbl.empty:
        for r in tbl[tbl.depth > 0].sort_values("cost", ascending=False).itertuples():
            sources[r.key] = f"{COLORS[r.color]} · {r.opening} · {r.line}"
    src = st.selectbox("מה לתרגל?", list(sources), format_func=sources.get, key="pr_src")
    if src == "mistakes":
        items = sorted(recurring([p for p in probs if p["status"] != "learned"]), key=SORTS["default"])[:15]
        if C.lichess_token():
            works = [p for p in items if (level_view(p) or {}).get("works")]
            if works:
                st.caption(f"לא נכללו {len(works)} מסעים ש־Stockfish מחשיב טעות אבל עובדים ברמה שלך "
                           f"(למשל {works[0]['played']} ב־{works[0]['opening']}). אפשר לראות אותם בטעויות החוזרות.")
                items = [p for p in items if p not in works]
    else:
        op = tbl[tbl.key == src].iloc[0]
        ids = set(node_games(op).id)
        items = sorted(recurring([p for p in probs if p["color"] == op.color and p["status"] != "learned"
                                  and ids & set(p["games"])]), key=SORTS["default"])
    if not items:
        empty("אין כאן טעויות שחוזרות על עצמן (או שכולן נלמדו). 🎉")
        return

    sig = f"{src}|{len(items)}|{colors}"
    if st.session_state.get("pr_sig") != sig:
        st.session_state.update(pr_sig=sig, pr_i=0, pr_ok=0, pr_n=0, pr_answer=None)
    i, ok, n = st.session_state.pr_i, st.session_state.pr_ok, st.session_state.pr_n

    if i >= len(items):
        with st.container(border=True, key="card_done"):
            md(f'<div style="text-align:center;padding:20px"><div style="font-size:3rem">🏁</div>'
               f'<div class="card-h" style="justify-content:center"><span class="t" style="font-size:1.4rem">סיימת את הסבב!</span></div>'
               f'<div class="kpi" style="border:none;min-height:0"><div class="v">{ok} / {n}</div><div class="s">תשובות נכונות</div></div></div>')
            st.button("סבב נוסף", type="primary", on_click=set_state, args=("pr_sig", None), width="stretch")
        return

    st.progress(i / len(items), text=f"עמדה {i + 1} מתוך {len(items)} · {ok} נכונות עד עכשיו")
    p = items[i]
    board = chess.Board(p["fen"])
    rng = random.Random(p["key"] + p["played"])
    others = [m for m in (board.san(m) for m in board.legal_moves) if m not in (p["best_san"], p["played"])]
    opts = [p["best_san"], p["played"]] + rng.sample(others, min(2, len(others)))
    rng.shuffle(opts)
    ans = st.session_state.pr_answer

    with st.container(border=True, key="card_quiz"):
        a, b = st.columns([1.15, 1], gap="large")
        with a:
            st.image(board_svg(board, p["color"], None, [(p["played_uci"], RED), (p["best_uci"], GREEN)] if ans else []),
                     width=460)
            if ans:
                md(arrow_legend())
        with b:
            md(f'<div class="card-h">{chip(p["color"])}<span class="t">{en(p["opening"])}</span></div>'
               f'{moves_html(p["pre_moves"])}'
               f'<div class="card-h" style="margin-top:14px"><span class="t" style="font-size:1.2rem">'
               f'תור ה{COLORS[p["color"]]}. מה המסע הטוב ביותר?</span></div>')
            if ans:
                cells = []
                for m in opts:
                    cls = "good" if m == p["best_san"] else "bad" if m == ans else "plain"
                    mark = "✓ " if cls == "good" else "✗ " if cls == "bad" else ""
                    cells.append(f'<div class="{cls}"><div class="v">{mark}{esc(m)}</div></div>')
                md(f'<div class="cmp opts">{"".join(cells)}</div>')
            else:
                g = st.columns(2)
                for j, m in enumerate(opts):
                    g[j % 2].button(m, key=f"opt_{sig}_{i}_{j}", on_click=answer, args=(m, p["best_san"]), width="stretch")
            if ans:
                if ans == p["best_san"]:
                    st.success(f"נכון! {p['best_san']} הוא המסע ש־Stockfish ממליץ עליו.", icon=":material/check_circle:")
                elif ans == p["played"]:
                    st.error(f"זה בדיוק המסע ששיחקת במשחקים ({p['mistakes']} מתוך {p['reached']} פעמים). "
                             f"עדיף {p['best_san']}.", icon=":material/cancel:")
                else:
                    st.warning(f"לא זה. המסע המומלץ הוא {p['best_san']}; במשחקים שיחקת {p['played']}.", icon=":material/info:")
                md('<div class="note">ייתכן שגם מסע אחר סביר – הבדיקה היא מול המסע הראשון של Stockfish.</div>'
                   + game_links(p["games"], p["color"], p["ply"], 6))
                st.button("לעמדה הבאה", type="primary", on_click=next_q, width="stretch", icon=":material/arrow_back:")
            else:
                md(f'<div class="note">כאן טעית ב‑{p["mistakes"]} מתוך {p["reached"]} הפעמים שהגעת לעמדה.</div>')


# ---------------------------------------------------------------- weaknesses
WEAK_CSS = """<style>
.witem{padding:10px 0;border-top:1px solid var(--gray-50);} .witem:first-of-type{border-top:none;}
.wtitle{font-weight:700;font-size:.95rem;margin:4px 0 2px;} .wtitle.red{color:var(--red);} .wtitle.green{color:var(--green);}
</style>"""


def non_overlapping(rows, n):
    """Up to n tree rows, skipping any whose ancestor or descendant is already picked (they share games)."""
    picked = []
    for r in rows:
        if all(not (r.group.startswith(q.group + " ") or q.group.startswith(r.group + " ")) for q in picked):
            picked.append(r)
        if len(picked) == n:
            break
    return picked


def weak_item(r, tone):
    label, ctone = CONF[r.conf]
    err = (f' · טעות נפוצה: <span class="ltr">{esc(r.top_error)}</span> ב‑{r.top_error_count} משחקים'
           if r.top_error and r.top_error_count >= 2 else "")
    return (f'<div class="witem"><div class="card-h"><span class="t">{en(r.opening)}</span>'
            f'<span class="badge b-{ctone}">{label}</span></div>'
            f'<div class="moves" style="line-height:1.6">{esc(r.line)}</div>'
            f'<div class="note"><b style="color:var(--{tone})">{pct(r.score)}</b> לעומת ממוצע של {pct(r.base)} '
            f'(<span dir="ltr">{r.diff * 100:+.0f}%</span>) ב‑{r.games} משחקים{err}</div></div>')


def line_tail(group, plies=4):
    """Last moves of a line with move numbers ('…3.Bc4 Nf6 4.d3'), enough to tell sibling lines apart."""
    toks = group.split()
    k = max(0, len(toks) - plies)
    tail = " ".join(move_label(i, m) if i % 2 or i == k + 1 else m for i, m in enumerate(toks[k:], k + 1))
    return ("…" if k else "") + tail


def weak_chart(t):
    d = t.sort_values("diff").reset_index(drop=True)
    # labels must be unique for the y axis; zero-width spaces keep look-alike rows apart
    d["label"] = [f"{o[:28]}{'…' if len(o) > 28 else ''}  ·  {line_tail(g)}" + "​" * i
                  for i, (o, g) in enumerate(zip(d.opening, d.group))]
    d["pp"] = d["diff"] * 100
    d["kind"] = ["weak" if x < 0 else "strong" for x in d.pp]
    d["alpha"] = d.conf.map({"high": 1.0, "mid": .7, "low": .35})
    d["conf_label"] = d.conf.map(lambda c: CONF[c][0])
    bars = alt.Chart(d).mark_bar(cornerRadius=3, size=14).encode(
        y=alt.Y("label:N", sort=list(d.label), title=None,
                axis=alt.Axis(orient="right", labelLimit=340, labelFontSize=12, ticks=False, domain=False)),
        x=alt.X("pp:Q", title="נקודות אחוז מול הממוצע בצבע", axis=alt.Axis(format="+.0f", grid=True)),
        color=alt.Color("kind:N", scale=alt.Scale(domain=["weak", "strong"], range=["#ef4444", "#22c55e"]), legend=None),
        opacity=alt.Opacity("alpha:Q", scale=None, legend=None),
        tooltip=[alt.Tooltip("opening:N", title="פתיחה"), alt.Tooltip("line:N", title="מסעים"),
                 alt.Tooltip("games:Q", title="משחקים"), alt.Tooltip("score:Q", title="אחוז נקודות", format=".0%"),
                 alt.Tooltip("base:Q", title="ממוצע בצבע", format=".0%"),
                 alt.Tooltip("pp:Q", title="פער", format="+.0f"), alt.Tooltip("conf_label:N", title="ודאות")])
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#9ca3af").encode(x="x:Q")
    return (bars + zero).properties(height=24 * len(d) + 30)


def summary_list(t, picked, sign, tone):
    """Confident openings; when there are none, the two leading candidates, clearly marked as possibly chance."""
    if picked:
        return "".join(weak_item(r, tone) for r in picked)
    cand = t[(t["diff"] * sign > 0) & (t.games >= C.CONF_MID_GAMES)].sort_values("z", ascending=sign < 0)
    cand = non_overlapping(cand.itertuples(), 2)
    head = ("אין חולשה מובהקת." if sign < 0 else "אין חוזקה מובהקת.")
    if not cand:
        return f'<div class="note">{head} כל הפתיחות קרובות לממוצע.</div>'
    return (f'<div class="note">{head} הבולטות ביותר, שעדיין עשויות להיות מקריות:</div>'
            + "".join(weak_item(r, tone) for r in cand))


def open_selected(k):
    if st.session_state.get(k):
        go("openings", st.session_state[k])


def page_weak():
    md(WEAK_CSS)
    section(you("נקודות החולשה שלך בפתיחות", f"נקודות החולשה של {esc(user)} בפתיחות"),
            f"כל פתיחה מושווית לאחוז הנקודות הממוצע {you('שלך', f'של {esc(user)}')} באותו צבע, כך שרואים איפה התוצאות "
            "נופלות או עולות ביחס לרמה הרגילה. החישוב מבוסס על תוצאות המשחקים בלבד, בלי מנוע. "
            "\"ודאות\" בודקת אם הפתיחה באמת שונה משאר המשחקים באותו צבע (מבחן z לשני שיעורים). מאחר שנבדקות עשרות פתיחות "
            f"במקביל הספים מחמירים: ודאות גבוהה דורשת {en(f'|z| ≥ {C.CONF_HIGH_Z}')} ולפחות {C.CONF_HIGH_GAMES} משחקים, "
            f"בינונית {en(f'|z| ≥ {C.CONF_MID_Z}')} ולפחות {C.CONF_MID_GAMES} משחקים. כל השאר מסומן \"ייתכן מקרי\". "
            "אותו כלל קובע גם את התווית \"בעייתית\" בשאר המסכים.")
    if tbl.empty:
        empty(f"אין פתיחה ששוחקה לפחות {C.MIN_GROUP_GAMES} פעמים בסינון הנוכחי.")
        return
    for c in colors:
        t = tbl[tbl.color == c]
        if t.empty:
            continue
        sure = t[t.conf != "low"]
        weak = non_overlapping(sure[sure["diff"] < 0].sort_values("diff").itertuples(), 3)
        strong = non_overlapping(sure[sure["diff"] > 0].sort_values("diff", ascending=False).itertuples(), 3)
        with st.container(border=True, key=f"card_weak_{c}"):
            md(f'<div class="card-h">{chip(c)}<span class="t" style="font-size:1.2rem">{WITH_COLOR[c]}</span>'
               f'<span class="muted small">ממוצע {pct(t.base.iat[0])} ב‑{int((fdf.color == c).sum()):,} משחקים</span></div>')
            a, b = st.columns(2, gap="large")
            with a:
                md('<div class="wtitle red">▼ חולשות</div>' + summary_list(t, weak, -1, "red"))
            with b:
                md('<div class="wtitle green">▲ חוזקות</div>' + summary_list(t, strong, 1, "green"))
            md(f'<div class="note" style="margin-top:14px"><b>כל הפתיחות ב{COLORS[c]}, מהחלשה לחזקה</b> · '
               'צבע חזק = ודאות גבוהה, חיוור = ייתכן מקרי. כל שורה כוללת גם את ההמשכים שלה.</div>')
            st.altair_chart(weak_chart(t), width="stretch")
            names = {r.key: f"{r.opening} · {r.line} ({r.diff * 100:+.0f}%)" for r in t.sort_values("diff").itertuples()}
            st.selectbox("לפרטים ולטעויות בפתיחה", list(names), format_func=names.get, index=None,
                         placeholder="בחרו פתיחה כדי לפתוח אותה במסך הפתיחות", key=f"wk_{c}",
                         on_change=open_selected, args=(f"wk_{c}",))


{"overview": page_overview, "weak": page_weak, "openings": page_openings, "mistakes": page_mistakes,
 "practice": page_practice}[page]()
