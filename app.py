"""Streamlit dashboard: opening analysis for a Lichess player (Hebrew, RTL)."""
import html
import random

import altair as alt
import chess
import chess.svg
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.stats import (SORTS, load_results, move_label, occurrences, opening_table, overall, prepare,
                            problem_positions, san_of, study_pgn)

st.set_page_config(page_title=f"ניתוח פתיחות · {C.USER}", page_icon="♞", layout="wide")

COLORS = {"white": "לבן", "black": "שחור"}
WITH_COLOR = {"white": "עם הלבנים", "black": "עם השחורים"}
SPEEDS = {"bullet": "בוליט", "blitz": "בליץ", "rapid": "רפיד", "classical": "קלאסי"}
RESULTS = {"win": "ניצחון", "draw": "תיקו", "loss": "הפסד"}
STATUS = {  # learning status -> (label, tone, explanation)
    "repeating": ("עדיין חוזרת", "red", "בפעם האחרונה שהגעת לעמדה הזו שיחקת שוב את אותו מסע."),
    "improving": ("בדרך לתיקון", "amber", "בביקורים האחרונים לא חזרת על הטעות, אבל עוד מוקדם לקבוע."),
    "learned": ("נלמדה", "green", f"מאז הטעות האחרונה הגעת לעמדה {C.LEARN_FIXED_AFTER}+ פעמים ולא חזרת עליה."),
    "few": ("מעט נתונים", "gray", f"הגעת לעמדה הזו פחות מ‑{C.LEARN_MIN_REACHED} פעמים, אז עוד אי אפשר לקבוע מגמה."),
}
PAGES = {"overview": "סקירה", "openings": "הפתיחות שלי", "mistakes": "טעויות חוזרות", "practice": "תרגול"}
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
@st.cache_data(show_spinner="טוען את המשחקים...")
def get_data():
    return load_results()


@st.cache_data(show_spinner=False)
def get_occ():
    return occurrences(get_data()[0])


@st.cache_data(show_spinner="מחשב סטטיסטיקות...")
def get_view(colors: tuple, speeds: tuple):
    """Filtered games (with each game's first error after its opening line), those errors, and the opening tree."""
    games, errors = get_data()
    g, rel, tree = prepare(games[games.color.isin(colors) & games.speed.isin(speeds)], errors)
    return g, rel, opening_table(g, errors[errors.id.isin(g.id)], tree)


@st.cache_data(show_spinner="מחפש טעויות חוזרות...")
def get_problems(colors: tuple, speeds: tuple):
    """All mistakes (position + move played) in the filter, both colours."""
    g, rel, _ = get_view(colors, speeds)
    occ = get_occ()
    occ = occ[occ.id.isin(g.id)]
    return [p for c in colors for p in problem_positions(g, rel, occ, c)]


@st.cache_data(show_spinner=False)
def explorer(fen, rating):
    from chessapp.explorer import lookup
    return lookup(fen, rating)


# ---------------------------------------------------------------- html helpers
def esc(t):
    return html.escape(str(t))


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
        if i % 2:
            out.append(f'<span class="n">{(i + 1) // 2}.</span>')
        cls = "err" if i == err else "cur" if i == cur else "dim" if upto is not None and i > upto else ""
        out.append(f'<span class="m {cls}">{esc(san)}</span>')
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
    return ('<div class="legend"><span><i style="background:#dc2626"></i>המסע ששיחקת</span>'
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
    return ('<div class="note"><b>מה משחקים שחקנים ברמה שלך (Lichess)</b></div>'
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


# ---------------------------------------------------------------- load + filters
try:
    df, all_errors = get_data()
except Exception:
    st.error("לא נמצאו תוצאות ניתוח. הריצו קודם בטרמינל: python run_all.py")
    st.stop()

avail = [s for s in SPEEDS if s in set(df.speed)] + sorted(set(df.speed) - set(SPEEDS))

with st.sidebar:
    md(f'<div class="brand">♞ ניתוח <span>פתיחות</span></div>')
    pick = st.segmented_control("אני משחק עם", ["all", "white", "black"], default="all", key="f_color",
                                format_func={"all": "שני הצבעים", **COLORS}.get, width="stretch")
    colors = [pick] if pick in COLORS else list(COLORS)
    if len(avail) > 1:
        speeds = st.multiselect("קצב משחק", avail, avail, format_func=lambda s: SPEEDS.get(s, s))
    else:
        speeds = avail
        st.caption(f"כל המשחקים בקצב {SPEEDS.get(avail[0], avail[0])}.")
    st.divider()
    with st.expander("איך לקרוא את הנתונים", icon=":material/help:"):
        md(f"""<dl class="gloss">
<dt>אחוז נקודות</dt><dd>ניצחון = נקודה, תיקו = חצי. 50% = מאזן שוויוני.</dd>
<dt>סיכויי ניצחון</dt><dd>הערכת המנוע מתורגמת לסיכוי (0–100%) לפי הנוסחה של Lichess. 50% = עמדה שקולה.</dd>
<dt>טעות בפתיחה</dt><dd>מסע ב‑{C.ANALYZE_PLIES // 2} המסעים הראשונים שלך שמוריד את סיכויי הניצחון ב‑{C.ERROR_WIN_DROP}% או יותר.
מסעים שהם חלק מקו הפתיחה שאתה משחק קבוע (למשל גמביט) לא נחשבים טעות.</dd>
<dt>נקודות שאבדו</dt><dd>כמה נקודות הפתיחה עלתה לך לעומת הממוצע שלך באותו צבע: משחקים × (הממוצע − אחוז הנקודות בפתיחה).</dd>
<dt>פתיחה בעייתית</dt><dd>אחוז נקודות נמוך ב‑{C.TOXIC_MARGIN:.0%} לפחות מהממוצע שלך באותו צבע, טעות עד מסע {C.EARLY_ERROR_MOVE} ב‑{C.EARLY_ERROR_SHARE:.0%} או יותר מהמשחקים,
וגם אותה טעות בדיוק ב‑{C.MIN_PROBLEM_GAMES} משחקים לפחות.</dd>
<dt>עץ הפתיחות</dt><dd>כל שורה כוללת את כל המשחקים שהתחילו ברצף הזה, כולל ההמשכים שלה.</dd>
<dt>טעות חוזרת</dt><dd>אותו מסע שגוי באותה עמדה ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר.</dd>
<dt>טעות שנלמדה</dt><dd>{STATUS["learned"][2]}</dd>
</dl>""")
    st.caption(f"Stockfish, עומק {C.ENGINE_DEPTH} קבוע לכל עמדה. פתיחה מוצגת רק אם שיחקת אותה {C.MIN_GROUP_GAMES}+ פעמים.")

if df[df.color.isin(colors) & df.speed.isin(speeds)].empty:
    empty("אין משחקים שמתאימים לסינון. שנו את הבחירה בסרגל הצד.")
    st.stop()
fdf, rel, tbl = get_view(tuple(colors), tuple(speeds))
probs = get_problems(tuple(colors), tuple(speeds))


def node_games(op):
    """All filtered games that start with the node's moves (the node row sums its whole subtree)."""
    pre = op.group.split()
    return fdf[(fdf.color == op.color) & fdf.line.str.split().map(lambda s: s[:len(pre)] == pre)]

# ---------------------------------------------------------------- header
by_time = df[df.speed.isin(speeds)].sort_values("created")
first_d, last_d = by_time.created.iat[0], by_time.created.iat[-1]
r_now, r_change = int(by_time.rating.iat[-1]), int(by_time.rating.iat[-1] - by_time.rating.iat[0])
trend = f'<span class="{"up" if r_change >= 0 else "down"}">{"▲" if r_change >= 0 else "▼"} {abs(r_change)} בתקופה</span>'
speed_txt = SPEEDS.get(speeds[0], speeds[0]) if len(speeds) == 1 else ""
md(f"""<div class="hero"><div><div class="eyebrow">LICHESS · {esc(C.USER)}</div><h1>ניתוח הפתיחות שלך</h1>
<p>{len(fdf):,} משחקי {speed_txt} · {fmt_date(first_d)} – {fmt_date(last_d)} · {C.ANALYZE_PLIES // 2} המסעים הראשונים בכל משחק נבדקו במנוע Stockfish</p></div>
<div class="rating"><div class="k">דירוג נוכחי</div><div class="v">{r_now}</div>{trend}</div></div>""")

if "page" not in st.session_state:
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
        rows.append(("הפתיחה הכי מוצלחת", f'{esc(best.opening)} · {pct(best.score)}'))
        rows.append(("הפתיחה שהכי עולה לך", f'{esc(worst.opening)} · {pct(worst.score)}'))
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

    section("על מה כדאי לעבוד קודם",
            "הפתיחות שעולות לך הכי הרבה נקודות ביחס לממוצע שלך באותו צבע – שיפור בהן ישפיע הכי מהר על התוצאות.")
    top = focus_openings(3)
    if top.empty:
        empty("אין פתיחה שמורידה את הממוצע שלך. יפה!")
    else:
        cols = st.columns(len(top))
        for i, (col, r) in enumerate(zip(cols, top.itertuples())):
            with col, st.container(border=True, key=f"card_focus_{i}", height="stretch"):
                err = (f'<div class="note">הטעות הנפוצה: <span class="ltr">{esc(r.top_error)}</span> '
                       f'(ב‑{pct(r.top_error_share)} מהמשחקים)</div>') if r.top_error else ""
                md(f'<div class="card-h"><span class="rank">{i + 1}</span>{chip(r.color)}'
                   f'{"<span class=\'badge b-red\'>בעייתית</span>" if r.toxic else ""}</div>'
                   f'<div class="card-h"><span class="t">{esc(r.opening)}</span></div>'
                   f'<div class="moves" style="line-height:1.6">{esc(r.line)}</div>'
                   f'<div class="stats s3"><div><div class="k">אחוז נקודות</div><div class="v">{pct(r.score)}</div></div>'
                   f'<div><div class="k">נקודות שאבדו</div><div class="v" style="color:var(--red)">{r.cost:.1f}</div></div>'
                   f'<div><div class="k">משחקים</div><div class="v">{r.games}</div></div></div>{err}')
                st.button("לטעויות בפתיחה הזו", key=f"focus_{i}", on_click=go, args=("openings", r.key),
                          icon=":material/arrow_back:", width="stretch")

    rec = [p for p in probs if p["count"] >= C.MIN_PROBLEM_GAMES and p["status"] != "learned"]
    if rec:
        with st.container(border=True, key="card_cta"):
            a, b, c2 = st.columns([4, 1.3, 1.3], vertical_alignment="center")
            with a:
                rep = sum(p["status"] == "repeating" for p in rec)
                md(f'<div class="card-h"><span class="t">יש {len(rec)} טעויות שחזרת עליהן ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר</span></div>'
                   f'<div class="muted small">ב‑{rep} מהן טעית שוב גם בפעם האחרונה שהגעת לעמדה. אלה המקומות הכי קלים לתקן.</div>')
            b.button("לרשימת הטעויות", on_click=go, args=("mistakes",), width="stretch")
            c2.button("להתחיל לתרגל", on_click=go, args=("practice",), type="primary", width="stretch")

    a, b = st.columns(2, gap="large")
    with a:
        section("הדירוג לאורך זמן")
        st.altair_chart(chart_rating(), width="stretch")
    with b:
        section("באיזה מסע מגיעה הטעות הראשונה", "מספר המשחקים לפי המסע שבו טעית לראשונה")
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
               f'<div class="cmp"><div class="bad"><div class="k">שיחקת</div><div class="v">{esc(r.played_san)}</div></div>'
               f'<div class="good"><div class="k">עדיף</div><div class="v">{esc(best)}</div></div></div>'
               f'<div class="note">סיכויי הניצחון שלך לפי המנוע: <b>{r.win_before:.0f}%</b> לפני המסע ← <b>{r.win_after:.0f}%</b> אחרי.</div>'
               f'{arrow_legend()}')
        elif ply == err:
            md(f'<div class="card-h"><span class="t">אחרי הטעות</span></div>'
               f'<div class="note">החץ האדום מראה את המסע ששיחקת. לחצו "רגע הטעות" כדי לראות מה היה עדיף.</div>')
        else:
            md(f'<div class="card-h"><span class="t">מהלך המשחק</span></div>'
               f'<div class="note">עברו קדימה עד רגע הטעות, או לחצו "רגע הטעות" כדי לקפוץ ישר אליו.</div>')
        md('<div style="margin-top:14px"></div>' + moves_html(moves[:err], upto=err, cur=ply if ply < err else None, err=err))
        md(f'<div class="note" style="margin-top:12px">{RESULTS[r.result]} · {fmt_date(r.created)} · '
           f'<a href="https://lichess.org/{r.id}/{color}#{err}" target="_blank">פתיחת המשחק ב‑Lichess ↗</a></div>')


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
    section("עץ הפתיחות שלך",
            f"כל רצף ששיחקת לפחות {C.MIN_GROUP_GAMES} פעמים. כל שורה כוללת גם את ההמשכים שלה (המוזחים מתחתיה). "
            "בחרו שורה כדי לראות את הטעויות בה על הלוח.")
    if tbl.empty:
        empty("אין פתיחה ששוחקה מספיק פעמים בסינון הנוכחי.")
        return
    a, b, _ = st.columns([1.4, 1.4, 2])
    show = a.segmented_control("הצג", ["all", "toxic"], default="all", key="op_show",
                               format_func={"all": "כל הפתיחות", "toxic": f"רק בעייתיות ({int(tbl.toxic.sum())})"}.get)
    sort = b.selectbox("סדר", ["order", "cost", "score", "games"], key="op_sort",
                       format_func={"order": "לפי העץ", "cost": "הכי הרבה נקודות שאבדו", "score": "אחוז נקודות נמוך",
                                    "games": "הכי הרבה משחקים"}.get)
    t = tbl[tbl.toxic] if show == "toxic" else tbl
    t = t.sort_values(sort, ascending=sort in ("order", "score")).reset_index(drop=True)
    if t.empty:
        empty("אין פתיחות בעייתיות בסינון הנוכחי.")
        return
    tree = sort == "order" and show == "all"
    # the table is right-aligned, so the tree indent goes after the (left-to-right) name: deeper rows shift left
    view = pd.DataFrame({
        "צבע": t.color.map(COLORS),
        "פתיחה": [short_name(r) + ("  ⚠" if r.toxic else "") + (" ┘" + " " * (2 * r.depth - 1) if r.depth else "")
                  for r in t.itertuples()] if tree else [o + ("  ⚠" if x else "") for x, o in zip(t.toxic, t.opening)],
        "מסעים": LRM + t.line + LRM, "משחקים": t.games,
        "אחוז נקודות": t.score * 100, "מול הממוצע": (t.score - t.base) * 100, "נקודות שאבדו": t.cost,
        "הטעות הנפוצה": [f"{LRM}{e}{LRM} · ×{n}" if e else "—" for e, n in zip(t.top_error, t.top_error_count)]})
    key = f"op_table_{show}_{sort}_{st.session_state.get('op_nonce', 0)}"
    ev = rtl_table(view, on_select="rerun", selection_mode="single-row", key=key, height=min(38 + 35 * len(view), 460),
                   column_config={
                       "צבע": st.column_config.TextColumn(width=50, alignment="right"),
                       "פתיחה": st.column_config.TextColumn(width=285, alignment="right", help="⚠ = פתיחה בעייתית (ראו הסבר בסרגל הצד)"),
                       "מסעים": st.column_config.TextColumn(width=165, alignment="left"),
                       "משחקים": st.column_config.NumberColumn(width=60, help="כולל כל ההמשכים של הרצף"),
                       "אחוז נקודות": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%", width=105),
                       "מול הממוצע": st.column_config.NumberColumn(format="%+.0f%%", width=80, help="לעומת הממוצע שלך באותו צבע"),
                       "נקודות שאבדו": st.column_config.NumberColumn(format="%.1f", width=85, help="משחקים × (הממוצע באותו צבע − אחוז הנקודות בפתיחה)"),
                       "הטעות הנפוצה": st.column_config.TextColumn(width=105, alignment="right",
                                                                  help="הטעות הראשונה הנפוצה אחרי רצף הפתיחה, ובכמה משחקים היא קרתה")})
    if ev.selection.rows:
        st.session_state.op_key = t.key.iat[ev.selection.rows[0]]
    sel = st.session_state.get("op_key")
    op = tbl[tbl.key == sel].iloc[0] if sel in set(tbl.key) else t.iloc[0]
    opening_detail(op)


def opening_detail(op):
    color = op.color
    scope = node_games(op)
    diff = (op.score - op.base) * 100
    eco = f'<span class="badge b-gray">{esc(op.eco)}</span>' if op.eco else ""
    toxic = '<span class="badge b-red">⚠ בעייתית</span>' if op.toxic else ""
    with st.container(border=True, key="card_opening"):
        md(f'<div class="card-h">{chip(color)}<span class="t" style="font-size:1.3rem">{esc(op.opening)}</span>{eco}{toxic}</div>'
           f'{moves_html(op.group.split())}'
           f'<div class="stats"><div><div class="k">משחקים</div><div class="v">{op.games}</div></div>'
           f'<div><div class="k">אחוז נקודות</div><div class="v">{pct(op.score)}</div></div>'
           f'<div><div class="k">מול הממוצע שלך ב{COLORS[color]}</div><div class="v" style="color:{"var(--green)" if diff >= 0 else "var(--red)"}"><span dir="ltr">{diff:+.0f}%</span></div></div>'
           f'<div><div class="k">טעות עד מסע {C.EARLY_ERROR_MOVE}</div><div class="v">{pct(op.early_error_share)}</div></div></div>'
           f'{wdl(op.win, op.draw, op.loss)}')

        # navigate the tree: parent and children of this node
        kids = tbl[(tbl.color == color) & (tbl.parent == op.group)].sort_values("games", ascending=False)
        parent = tbl[(tbl.color == color) & (tbl.group == op.parent)] if op.parent else tbl.iloc[0:0]
        items = [(f"↑ חזרה אל {parent.opening.iat[0]}", parent.key.iat[0])] if len(parent) else []
        items += [(f"{short_name(k)} · {k.games} · {pct(k.score)}", k.key) for k in kids.head(7).itertuples()]
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
        hide = st.toggle("הסתר טעויות שכבר למדתי", True, key="op_hide")
        if hide:
            errs = errs[[not (i and i["status"] == "learned") for i in errs["info"]]]
        errs = errs.sort_values("drop", ascending=False).reset_index(drop=True)
        md(f'<div class="sec" style="margin-top:1.2rem"><h3>הטעויות בפתיחה הזו ({len(errs)})</h3>'
           f'<p>הטעות הראשונה בכל משחק אחרי רצף הפתיחה, מהיקרה לזולה. בחרו טעות כדי לראות אותה על הלוח.</p></div>')
        if errs.empty:
            empty("אין טעויות פתוחות בפתיחה הזו.")
            return
        ev = rtl_table(pd.DataFrame({
            "המסע שלך": [LRM + move_label(int(p), s) + LRM for p, s in zip(errs.first_error_ply, errs.played_san)],
            "עדיף": [LRM + (san_of(f, b) or "") + LRM for f, b in zip(errs.fen_before, errs.best)],
            "סיכויי ניצחון": [f"{a:.0f}% ← {b:.0f}%" for a, b in zip(errs.win_before, errs.win_after)],
            "חזרת על הטעות": [f"{i['mistakes']} מתוך {i['reached']}" if i else "—" for i in errs["info"]],
            "מצב": [STATUS[i["status"]][0] if i else "—" for i in errs["info"]],
            "תוצאה": errs.result.map(RESULTS), "תאריך": errs.created.map(fmt_date)}),
            on_select="rerun", selection_mode="single-row",
            key=f"errs_{op.key}_{hide}", height=min(38 + 35 * len(errs), 250),
            column_config={"סיכויי ניצחון": st.column_config.TextColumn(
                alignment="right", help="סיכויי הניצחון שלך לפי המנוע: לפני המסע ← אחריו")})
        r = errs.iloc[ev.selection.rows[0] if ev.selection.rows else 0]
        st.markdown("")
        board_viewer(r, color, op.key)


# ---------------------------------------------------------------- mistakes
def usual_html(p):
    """What the user usually plays in this position (all visits, not only the mistakes)."""
    moves = " · ".join(f'<span class="ltr">{esc(m)}</span> ×{c}' for m, c in list(p["moves"].items())[:4])
    if p["usual"] == p["played"]:
        head = f'<b>זה המסע הקבוע שלך כאן</b> ({p["usual_n"]} מתוך {p["reached"]} פעמים).'
    else:
        head = (f'בדרך כלל אתה משחק כאן <span class="ltr">{esc(p["usual"])}</span> '
                f'({p["usual_n"]} מתוך {p["reached"]}), והטעות היא סטייה.')
    return f'{head} כל המסעים ששיחקת בעמדה: {moves}'


def mistake_card(p, n):
    with st.container(border=True, key=f"card_mk_{n}"):
        a, b = st.columns([1, 1.35], gap="large")
        with a:
            st.image(board_svg(chess.Board(p["fen"]), p["color"], None,
                               [(p["played_uci"], RED), (p["best_uci"], GREEN)], size=400), width=400)
            md(arrow_legend())
        with b:
            _, _, why = STATUS[p["status"]]
            md(f'<div class="card-h"><span class="rank">#{n}</span>{chip(p["color"])}{badge(p["status"])}</div>'
               f'<div class="card-h"><span class="t">{esc(p["opening"])}</span></div>'
               f'{moves_html(p["pre_moves"])}'
               f'<div class="cmp"><div class="bad"><div class="k">שיחקת</div><div class="v">{esc(move_label(p["ply"], p["played"]))}</div></div>'
               f'<div class="good"><div class="k">עדיף לשחק</div><div class="v">{esc(move_label(p["ply"], p["best_san"] or "?"))}</div></div></div>'
               f'<div class="stats"><div><div class="k">חזרת על הטעות</div><div class="v">{p["mistakes"]} מתוך {p["reached"]}</div></div>'
               f'<div><div class="k">סיכויי ניצחון</div><div class="v">{p["win_before"]:.0f}% ← {p["win_after"]:.0f}%</div></div>'
               f'<div><div class="k">אחוז נקודות במשחקים</div><div class="v">{pct(p["score"])}</div></div>'
               f'<div><div class="k">פעם אחרונה</div><div class="v">{fmt_date(p["last_mistake"]) if p["last_mistake"] else "—"}</div></div></div>'
               f'<div class="note">{usual_html(p)}</div>'
               f'<div class="note">{why} '
               f'"חזרת על הטעות" = בכמה מהפעמים שהגעת לעמדה הזו שיחקת את אותו מסע.</div>'
               f'<div class="note" style="margin-top:10px">המשחקים:</div>{game_links(p["games"], p["color"], p["ply"])}')
            if C.LICHESS_TOKEN:
                rating = int(fdf[fdf.color == p["color"]].rating.median())
                ex = explorer(p["fen"], rating)
                if ex:
                    md(explorer_html(ex, p["color"]))


def page_mistakes():
    rec = [p for p in probs if p["count"] >= C.MIN_PROBLEM_GAMES]
    counts = {s: sum(p["status"] == s for p in rec) for s in STATUS}
    section("טעויות שחוזרות על עצמן",
            f"עמדות שבהן שיחקת את אותו מסע שגוי ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר. לכל טעות: איך הגעת לעמדה, מה שיחקת, "
            "מה עדיף, מה אתה משחק שם בדרך כלל, והאם הפסקת לחזור עליה.")
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
    if not items:
        empty("אין טעויות להצגה. 🎉")
        return
    a, b = st.columns([3, 1.3], vertical_alignment="center")
    a.caption("ייצוא העמדות כקובץ PGN: ב‑Lichess פותחים Study ← Add chapter ← PGN ומדביקים או מעלים את הקובץ. "
              "כל עמדה הופכת לפרק: המסע המומלץ הוא הקו הראשי והמסע ששיחקת – וריאציה.")
    b.download_button(f"ייצוא {len(items)} עמדות ל‑PGN", study_pgn(items), file_name="opening-mistakes.pgn",
                      mime="application/x-chess-pgn", icon=":material/download:", width="stretch")
    if not C.LICHESS_TOKEN:
        st.caption("כדי לראות גם מה משחקים שחקנים ברמה שלך בכל עמדה (Lichess Opening Explorer) צריך להגדיר LICHESS_TOKEN – "
                   "מאז 2025 ה‑API דורש טוקן. ראו README.")
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
            "שיחקת": [LRM + move_label(p["ply"], p["played"]) + LRM for p in items],
            "עדיף": [LRM + move_label(p["ply"], p["best_san"] or "?") + LRM for p in items],
            "הגעת לעמדה": [p["reached"] for p in items], "טעית": [p["mistakes"] for p in items],
            "שיעור טעות": [p["rate"] * 100 for p in items], "מצב": [STATUS[p["status"]][0] for p in items],
            "בדרך כלל": [LRM + p["usual"] + LRM for p in items],
            "ירידה בסיכויים": [p["avg_drop"] for p in items], "פעם אחרונה": [p["last_mistake"] for p in items]}),
            column_config={"שיעור טעות": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
                           "בדרך כלל": st.column_config.TextColumn(alignment="right", help="המסע שאתה משחק הכי הרבה בעמדה הזו"),
                           "ירידה בסיכויים": st.column_config.NumberColumn(format="%.0f%%", help="ממוצע הירידה בסיכויי הניצחון")})


# ---------------------------------------------------------------- practice
def answer(choice, best):
    st.session_state.pr_answer = choice
    st.session_state.pr_n += 1
    st.session_state.pr_ok += int(choice == best)


def next_q():
    st.session_state.pr_i += 1
    st.session_state.pr_answer = None


def page_practice():
    section("תרגול", "העמדות שבהן טעית. מצאו את המסע הטוב ביותר – כמו במשחק אמיתי.")
    sources = {"mistakes": "הטעויות החוזרות שלי"}
    if not tbl.empty:
        for r in tbl[tbl.depth > 0].sort_values("cost", ascending=False).itertuples():
            sources[r.key] = f"{COLORS[r.color]} · {r.opening} · {r.line}"
    src = st.selectbox("מה לתרגל?", list(sources), format_func=sources.get, key="pr_src")
    if src == "mistakes":
        items = sorted((p for p in probs if p["status"] != "learned"), key=SORTS["default"])[:15]
    else:
        op = tbl[tbl.key == src].iloc[0]
        ids = set(node_games(op).id)
        items = sorted((p for p in probs if p["color"] == op.color and p["status"] != "learned" and ids & set(p["games"])),
                       key=SORTS["default"])
    if not items:
        empty("אין עמדות לתרגול כאן – כל הטעויות נלמדו. 🎉")
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
            md(f'<div class="card-h">{chip(p["color"])}<span class="t">{esc(p["opening"])}</span></div>'
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
                    st.success(f"נכון! {p['best_san']} הוא המסע ש‑Stockfish ממליץ עליו.", icon=":material/check_circle:")
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


{"overview": page_overview, "openings": page_openings, "mistakes": page_mistakes, "practice": page_practice}[page]()
