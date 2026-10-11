"""רפרטואר: weak and strong openings per colour, and the opening tree with each node's mistakes."""
import altair as alt
import pandas as pd
import streamlit as st

from chessapp import config as C

from .common import (COLORS, CONF, LRM, WITH_COLOR, chip, clip, empty, en, esc, md, move_label, moves_html, pct,
                     rtl_table, status_map, tail_moves, wdl, you)
from .ctx import ctx
from .data import tr_key
from .plan import focus_openings, node_games, non_overlapping, short_name, summary_list



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


def select_node(key):
    st.session_state.op_key = key


def _summary(c):
    t = ctx.tbl[ctx.tbl.color == c]
    if t.empty:
        return
    sure = t[t.conf != "low"]
    weak = non_overlapping(sure[sure["diff"] < 0].sort_values("diff").itertuples(), 3)
    strong = non_overlapping(sure[sure["diff"] > 0].sort_values("diff", ascending=False).itertuples(), 3)
    with st.container(border=True, key=f"card_weak_{c}"):
        md(f'<div class="card-h">{chip(c)}<span class="t" style="font-size:1.2rem">{WITH_COLOR[c]}</span>'
           f'<span class="muted small">ממוצע {pct(t.base.iat[0])} ב‑{int((ctx.fdf.color == c).sum()):,} משחקים</span></div>')
        a, b = st.columns(2, gap="large")
        with a:
            md('<div class="wtitle red">▼ איפה אתה מפסיד נקודות</div>' + summary_list(t, weak, -1, "red"))
        with b:
            md('<div class="wtitle green">▲ איפה אתה חזק</div>' + summary_list(t, strong, 1, "green"))
        if st.toggle("הצג גרף", False, key=f"rp_chart_{c}"):
            st.altair_chart(weak_chart(t), width="stretch")


def _tree_table():
    tbl = ctx.tbl
    t = tbl.reset_index(drop=True)
    both = len(ctx.colors) == 2
    mark = {"white": "○ ", "black": "● "}
    names = []
    for r in t.itertuples():
        base = clip(short_name(r), max(14, 28 - 2 * r.depth)) + ("  ⚠" if r.toxic else "")
        names.append((mark[r.color] if both else "") + base + (" ┘" + " " * r.depth if r.depth else ""))
    view = pd.DataFrame({"פתיחה": names, "מסעים": [LRM + tail_moves(g) + LRM for g in t.group], "משחקים": t.games,
                         "ניקוד": t.score * 100, "מול הממוצע": (t.score - t.base) * 100})
    key = f"op_table_{st.session_state.get('op_nonce', 0)}_{st.session_state.get('op_key', '')}"
    ev = rtl_table(view, on_select="rerun", selection_mode="single-row", key=key, height=min(38 + 35 * len(view), 420),
                   column_config={
                       "פתיחה": st.column_config.TextColumn(width=235, alignment="right",
                                                            help="⚠ = פתיחה בעייתית. כל שורה כוללת גם את ההמשכים שלה."),
                       "מסעים": st.column_config.TextColumn(width=175, alignment="left"),
                       "משחקים": st.column_config.NumberColumn(width=60),
                       "ניקוד": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%", width=105,
                                                                help="אחוז נקודות: ניצחון = 1, תיקו = ½"),
                       "מול הממוצע": st.column_config.NumberColumn(
                           format="%+.0f%%", width=80,
                           help=you("לעומת הממוצע שלך באותו צבע", "לעומת הממוצע של השחקן באותו צבע"))})
    if ev.selection.rows:
        st.session_state.op_key = t.key.iat[ev.selection.rows[0]]
    sel = st.session_state.get("op_key")
    if sel not in set(tbl.key):  # first visit: the line that costs the most points
        top = focus_openings(1)
        sel = top.key.iat[0] if len(top) else t.key.iat[0]
    return tbl[tbl.key == sel].iloc[0]


def _node_mistakes(op):
    diff = (op.score - op.base) * 100
    toxic = '<span class="badge b-red">⚠ בעייתית</span>' if op.toxic else ""
    with st.container(border=True, key="card_opening"):
        md(f'<div class="card-h">{chip(op.color)}<span class="t" style="font-size:1.2rem">{en(op.opening)}</span>{toxic}</div>'
           f'{moves_html(op.group.split())}'
           f'<div class="note"><b>{pct(op.score)}</b> ב‑{op.games} משחקים, '
           f'<span dir="ltr">{diff:+.0f}%</span> מהממוצע {you("שלך", "של השחקן")} ב{COLORS[op.color]}.</div>'
           f'{wdl(op.win, op.draw, op.loss, legend=False)}')
        if not ctx.analyzed:
            md('<div class="note" style="margin-top:12px">הטעויות עוד לא נותחו במנוע. אפשר להפעיל את הניתוח מההגדרות (⚙).</div>')
            return
        ids = set(node_games(op).id)
        found = sorted((p for p in ctx.probs if p["color"] == op.color and ids & set(p["games"])
                        and p["status"] != "learned"), key=lambda p: (-p["count"], -p["cost"]))
        md(f'<div class="sec" style="margin:1rem 0 .4rem"><h3 style="font-size:1.05rem">הטעויות בפתיחה הזו ({len(found)})</h3></div>')
        if not found:
            md('<div class="note">אין כאן טעויות פתוחות בסף הנוכחי.</div>')
        for i, p in enumerate(found[:8]):
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
    md(f'<h1 class="plan-h1">{you("הרפרטואר שלך", "הרפרטואר של " + esc(ctx.user))}</h1>'
       '<p class="plan-sub">איפה התוצאות נופלות או עולות ביחס לממוצע, ובכל פתיחה: מה הטעויות.</p>')
    for c in ctx.colors:
        _summary(c)
    md('<div class="sec"><h3>עץ הפתיחות</h3><p>בחרו שורה כדי לראות את הטעויות בה.</p></div>')
    op = _tree_table()
    _node_mistakes(op)
