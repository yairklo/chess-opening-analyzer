"""הפתיחות שלי: weak and strong openings per colour, and the opening tree with each node's mistakes."""
import altair as alt
import chess
import pandas as pd
import streamlit as st

from chessapp import config as C

from .common import (COLORS, CONF, GREEN, LRM, RED, board_svg, clip, empty, esc, md, move_label, moves_html, pct, rtl_table,
                     status_map, tail_moves, wdl, you)
from .ctx import ctx
from .data import tr_key
from .names import he_title
from .plan import focus_openings, node_games, non_overlapping, short_name



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


def open_mistake(key):
    st.session_state.update(page="mistakes", mk_sel=key, mk_drill=False, quiz=False)


CONF_HE = {"high": ("בטוח", "green"), "mid": ("כנראה", "amber"), "low": ("מוקדם לדעת", "gray")}
CONF_HELP = ("ההבדל מהממוצע שלך: \"בטוח\" = הרבה משחקים והבדל ברור, \"כנראה\" = סביר, "
             "\"מוקדם לדעת\" = מעט משחקים או הבדל קטן, ואפשר שהוא מקרי.")


def _rows(rows, tone):
    out = []
    for r in rows:
        label, ctone = CONF_HE[r.conf]
        out.append(
            f'<div class="orow"><div dir="ltr" style="text-align:right"><div class="nm">{esc(clip(r.opening, 34))}</div>'
            f'<div class="moves" style="font-size:.78rem;line-height:1.5">{esc(tail_moves(r.group, 30))}</div></div>'
            f'<div style="display:flex;align-items:center;gap:10px;white-space:nowrap">'
            f'<span class="pill {ctone}" title="{esc(CONF_HELP)}">{label}</span>'
            f'<span class="muted small">{r.games} משחקים</span>'
            f'<span class="sc" style="color:var(--{tone})">{pct(r.score)}</span></div></div>')
    return "".join(out)


def _candidates(t, sign):
    """Confident openings; when there are none, the leading candidates (marked as possibly chance)."""
    sure = t[t.conf != "low"]
    picked = non_overlapping((sure[sure["diff"] * sign > 0].sort_values("diff", ascending=sign < 0)).itertuples(), 3)
    if picked:
        return picked, ""
    cand = t[(t["diff"] * sign > 0) & (t.games >= C.CONF_MID_GAMES)].sort_values("z", ascending=sign < 0)
    cand = non_overlapping(cand.itertuples(), 3)
    note = "אין עדיין הבדל מובהק. אלה הבולטות ביותר, ואפשר שהן מקריות." if cand else "כל הפתיחות קרובות לממוצע."
    return cand, note


def _summary(c):
    t = ctx.tbl[ctx.tbl.color == c]
    if t.empty:
        return
    weak, wnote = _candidates(t, -1)
    strong, snote = _candidates(t, 1)
    a, b = st.columns(2, gap="large")
    with a, st.container(border=True, key=f"card_strong_{c}", height="stretch"):
        md('<div class="plan-title" style="color:var(--green)">▲ חוזקות</div>'
           + (f'<div class="note">{snote}</div>' if snote else "") + _rows(strong, "green"))
    with b, st.container(border=True, key=f"card_weak_{c}", height="stretch"):
        md('<div class="plan-title" style="color:#dc2626">▼ חולשות</div>'
           + (f'<div class="note">{wnote}</div>' if wnote else "") + _rows(weak, "red"))
    if st.toggle("הצג גרף", False, key=f"rp_chart_{c}"):
        st.altair_chart(weak_chart(t), width="stretch")


def _tree_table(c):
    tbl = ctx.tbl
    t = tbl[tbl.color == c].reset_index(drop=True)
    names = []
    for r in t.itertuples():
        nm = clip(short_name(r), max(14, 30 - 2 * r.depth)) + ("  ⚠" if r.toxic else "")
        names.append(f"{tail_moves(r.group, 18)}  {nm}" + (" ┘" + " " * r.depth if r.depth else ""))
    with_error = [int(node_games(r).first_error_ply.notna().sum()) if ctx.analyzed else 0 for r in t.itertuples()]
    view = pd.DataFrame({
        "פתיחה": [LRM + n for n in names], "משחקים": t.games, "ציון": t.score * 100,
        "מול הממוצע": (t.score - t.base) * 100, "משחקים עם טעות": with_error})
    key = f"op_table_{c}_{st.session_state.get('op_nonce', 0)}_{st.session_state.get('op_key', '')}"
    ev = rtl_table(view, on_select="rerun", selection_mode="single-row", key=key, height=min(38 + 35 * len(view), 420),
                   column_config={
                       "פתיחה": st.column_config.TextColumn(width=320, alignment="right",
                                                            help="⚠ = פתיחה בעייתית. כל שורה כוללת גם את ההמשכים שלה."),
                       "משחקים": st.column_config.NumberColumn(width=70),
                       "ציון": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%", width=110,
                                                               help="אחוז נקודות: ניצחון = 1, תיקו = ½"),
                       "מול הממוצע": st.column_config.NumberColumn(
                           format="%+.0f%%", width=90,
                           help=you("לעומת הממוצע שלך באותו צבע", "לעומת הממוצע של השחקן באותו צבע")),
                       "משחקים עם טעות": st.column_config.NumberColumn(width=110)})
    if ev.selection.rows:
        st.session_state.op_key = t.key.iat[ev.selection.rows[0]]
    sel = st.session_state.get("op_key")
    if sel not in set(t.key):  # first visit: the line that costs the most points
        top = focus_openings(1)
        top = top[top.color == c]
        sel = top.key.iat[0] if len(top) else t.key.iat[0]
    return t[t.key == sel].iloc[0]


def _node_mistakes(op):
    diff = (op.score - op.base) * 100
    with st.container(border=True, key="card_opening"):
        toxic = ' <span class="pill red">בעייתית</span>' if op.toxic else ""
        md(f'<div class="plan-title">{esc(he_title(op.opening))}{toxic}</div>'
           f'<div class="plan-en" dir="ltr" style="text-align:right">{esc(op.opening)}</div>'
           f'{moves_html(op.group.split())}'
           f'<div class="note"><b>{pct(op.score)}</b> ב־{op.games} משחקים, '
           f'<span dir="ltr">{diff:+.0f}%</span> מהממוצע {you("שלך", "של השחקן")} ב{COLORS[op.color]}.</div>'
           f'{wdl(op.win, op.draw, op.loss, legend=False)}')
        if not ctx.analyzed:
            md('<div class="note" style="margin-top:12px">הטעויות עוד לא נותחו במנוע. אפשר להפעיל את הניתוח מההגדרות.</div>')
            return
        ids = set(node_games(op).id)
        found = sorted((p for p in ctx.probs if p["color"] == op.color and ids & set(p["games"])
                        and p["status"] != "learned"), key=lambda p: (-p["count"], -p["cost"]))
        md(f'<div class="plan-title" style="margin-top:14px;font-size:1rem">הטעויות בפתיחה הזו ({len(found)})</div>')
        if not found:
            md('<div class="note">אין כאן טעויות פתוחות ברגישות הנוכחית.</div>')
            return
        top = found[0]
        a, b = st.columns([1, 2], vertical_alignment="center")
        a.image(board_svg(chess.Board(top["fen"]), top["color"], None,
                          [(top["played_uci"], RED), (top["best_uci"], GREEN)], size=200), width=200)
        with b:
            md(f'<div class="plan-title" style="font-size:1rem">הטעות שחוזרת כאן</div>'
               f'<div class="plan-line"><b class="ltr">{esc(move_label(top["ply"], top["played"]))}</b> במקום '
               f'<b class="ltr">{esc(move_label(top["ply"], top["best_san"] or "?"))}</b> · '
               f'ב־{top["mistakes"]} מתוך {top["reached"]} משחקים</div>')
            st.button("לפתוח את הטעות ←", key=f"rp_open_{op.key}", on_click=open_mistake, args=(tr_key(top),),
                      type="primary")
        for i, p in enumerate(found[1:8], 1):
            a, b, c = st.columns([4, 2, 1.4], vertical_alignment="center")
            a.markdown(f'<span dir="ltr">{esc(move_label(p["ply"], p["played"]))}</span> ← '
                       f'<span dir="ltr">{esc(move_label(p["ply"], p["best_san"] or "?"))}</span>', unsafe_allow_html=True)
            b.caption(f'{status_map()[p["status"]][0]} · ' + (f'{p["count"]} פעמים' if p["count"] > 1 else "פעם אחת"))
            c.button("לטעות ←", key=f"rp_mk_{op.key}_{i}", on_click=open_mistake, args=(tr_key(p),), width="stretch")
        if len(found) > 8:
            st.caption(f"ועוד {len(found) - 8} טעויות. אפשר לראות את כולן במסך הטעויות.")


def page_repertoire():
    if ctx.tbl.empty:
        empty(f"אין פתיחה ששוחקה לפחות {C.MIN_GROUP_GAMES} פעמים בסינון הנוכחי.")
        return
    avail = [c for c in ctx.colors if not ctx.tbl[ctx.tbl.color == c].empty] or list(ctx.colors)
    head, pick_col = st.columns([3, 1.4], vertical_alignment="center")
    c = pick_col.segmented_control("צבע", avail, default=avail[0], key="rp_color", label_visibility="collapsed",
                                   format_func={"white": "○ לבן", "black": "● שחור"}.get, width="stretch")
    c = c if c in avail else avail[0]
    t = ctx.tbl[ctx.tbl.color == c]
    games = int((ctx.fdf.color == c).sum())
    head.markdown(f'<h1 class="plan-h1" style="margin-top:0">{you("הפתיחות שלך", "הפתיחות של " + esc(ctx.user))}</h1>'
                  f'<p class="plan-sub">איך אתה מצליח בכל פתיחה לעומת הממוצע שלך ב{COLORS[c]} '
                  f'({pct(t.base.iat[0])} ב־{games:,} משחקים).</p>', unsafe_allow_html=True)
    _summary(c)
    md('<div class="sec"><h3>כל הפתיחות</h3><p>בחרו שורה כדי לראות את הטעויות בה.</p></div>')
    op = _tree_table(c)
    _node_mistakes(op)
