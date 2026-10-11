"""Shared constants, CSS and HTML/board helpers for every screen."""
import html

import chess
import chess.svg
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.stats import move_label

from .ctx import ctx

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
CONF = {"high": ("ודאות גבוהה", "green"), "mid": ("ודאות בינונית", "amber"), "low": ("ייתכן מקרי", "gray")}
RED, GREEN = "#dc2626d0", "#16a34ad0"
LRM = "‎"  # keeps move sequences left-to-right inside RTL table cells

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600&display=swap');
:root{--ink:#111827;--muted:#6b7280;--soft:#9ca3af;--line:#e5e7eb;--card:#fff;--bg:#f6f7f9;
--blue:#2563eb;--blue-50:#eff6ff;--accent:#ff4b4b;--accent-50:#fff1f1;--green:#15803d;--green-50:#ecfdf3;--red:#dc2626;--red-50:#fef2f2;
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
.rank{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:var(--accent);color:#fff;font-weight:800;font-size:.9rem;}

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
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:none!important;}
.topline{font-weight:600;font-size:1rem;color:var(--ink);padding:.35rem 0;}
.topline .sep{color:var(--soft);margin:0 6px;}
.plan-h1{font-size:2rem;font-weight:800;margin:.6rem 0 .1rem;padding:0;color:var(--ink);}
.plan-sub{color:var(--muted);margin:0 0 1rem;font-size:.98rem;}
.plan-pos{color:var(--muted);font-size:.82rem;margin:2px 0 6px;}
.plan-text{font-size:.95rem;line-height:1.6;margin:6px 0;}
.plan-why{font-size:.86rem;color:#78350f;margin:4px 0 8px;}
.mk-h1{font-family:'JetBrains Mono',monospace;font-size:1.7rem;font-weight:800;margin:.5rem 0 .8rem;color:var(--ink);direction:rtl;text-align:right;}
.prog{display:flex;height:10px;border-radius:99px;overflow:hidden;background:var(--gray-50);margin:10px 0;direction:rtl;}
.prog span{display:block;height:100%;} .prog .r{background:#ef4444;} .prog .i{background:#f59e0b;} .prog .l{background:#22c55e;}
.orow{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid var(--gray-50);align-items:baseline;}
.orow:first-of-type{border-top:none;} .orow .nm{font-weight:600;} .orow .sc{font-weight:700;white-space:nowrap;}

.stApp{background:var(--bg);}
.st-key-topbar{background:#fff;border:1px solid var(--line);border-radius:14px;padding:.35rem 1rem;margin:0 0 1.1rem;}
.brand-top{font-weight:800;font-size:1.15rem;color:var(--ink);white-space:nowrap;}
.who{display:inline-flex;align-items:center;gap:8px;background:var(--gray-50);border-radius:99px;padding:5px 12px 5px 6px;font-size:.88rem;color:var(--ink);white-space:nowrap;}
.who .av{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;font-size:.82rem;}
.who .sep{color:var(--soft);}
.st-key-topbar [data-testid="stSegmentedControl"] button[aria-checked="true"],.st-key-topbar button[kind="segmented_controlActive"]{color:var(--accent)!important;}
.plan-title{font-weight:700;font-size:1.12rem;color:var(--ink);margin:0;line-height:1.3;}
.plan-en{color:var(--muted);font-size:.8rem;margin:2px 0 8px;direction:rtl;}
.plan-line{font-size:.9rem;margin:4px 0;color:var(--ink);} .plan-line b{font-weight:700;}
.plan-reason{font-size:.88rem;color:#374151;margin:10px 0;line-height:1.55;}
.pill{display:inline-flex;align-items:center;padding:3px 12px;border-radius:99px;font-size:.78rem;font-weight:700;}
.pill.red{background:var(--accent-50);color:#dc2626;} .pill.amber{background:var(--amber-50);color:var(--amber);}
.pill.green{background:var(--green-50);color:var(--green);} .pill.blue{background:var(--blue-50);color:var(--blue);} .pill.gray{background:var(--gray-50);color:var(--muted);}
.mk-crumb{color:var(--muted);font-size:.9rem;}
.mk-sub{color:var(--muted);font-size:.84rem;margin:.2rem 0;}
.cmp .s{font-size:.78rem;color:var(--muted);margin-top:2px;}
.arrow-sep{color:var(--soft);font-weight:400;margin:0 .35em;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def status_map():
    return STATUS_ME if ctx.me else STATUS_OTHER


def you(mine, theirs):
    """Second person for the default player, the player's name (or a neutral form) for anyone else."""
    return mine if ctx.me else theirs


def esc(t):
    return html.escape(str(t))


def ltr_label(before, name, after=""):
    """Widget label (plain text, no HTML) with an English name that keeps its place inside Hebrew text."""
    return f"⁧{before}⁦{name}⁩{after}⁩"


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
    label, tone, _ = status_map()[status]

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


BOARD_COLORS = {"square light": "#eeeed2", "square dark": "#769656", "square light lastmove": "#f6f669",
                "square dark lastmove": "#baca2b", "margin": "#ffffff", "coord": "#6b7280",
                "inner border": "#769656", "outer border": "#ffffff"}


def board_svg(board, color, last=None, arrows=(), size=460):
    ar = []
    for uci, clr in arrows:
        if uci:
            m = chess.Move.from_uci(uci)
            ar.append(chess.svg.Arrow(m.from_square, m.to_square, color=clr))
    check = board.king(board.turn) if board.is_check() else None
    return chess.svg.board(board, arrows=ar, lastmove=last, check=check, size=size, colors=BOARD_COLORS,
                           coordinates=size >= 300,
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


def set_state(k, v):
    st.session_state[k] = v



def line_html(sans, first_ply, cur):
    """Numbered line with the move currently on the board highlighted (cur = number of moves played, 0 = none)."""
    out = []
    for i, san in enumerate(sans, 1):
        ply = first_ply + i - 1
        num = f'<span class="n">{(ply + 1) // 2}.</span>' if ply % 2 else (f'<span class="n">{(ply + 1) // 2}...</span>' if i == 1 else "")
        cls = "cur" if i == cur else "dim" if i > cur else ""
        out.append(f'<span class="u">{num}<span class="m {cls}">{esc(san)}</span></span> ')
    return f'<div class="moves">{"".join(out)}</div>'
