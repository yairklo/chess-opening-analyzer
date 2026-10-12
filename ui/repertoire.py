"""הפתיחות שלי: weak and strong openings per colour, and the opening tree with each node's mistakes."""
import altair as alt
import chess
import pandas as pd
import streamlit as st

from chessapp import config as C

from .common import (COLORS, CONF, GREEN, LRM, RED, in_games, ltr_text, position_at, board_svg, clip, empty, esc, md, move_label, moves_html, pct, rtl_table,
                     status_map, tail_moves, wdl, you)
from .ctx import ctx
from .data import tr_key
from .names import he_title
from .plan import focus_openings, last_plies, node_games, non_overlapping, practice_position, short_name
from .trainer import drill



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


def start_practice(key):
    st.session_state.rp_drill = key


def stop_practice():
    st.session_state.rp_drill = None


TREE_ROWS = 6
CONF_HE = {"high": ("בטוח", "green"), "mid": ("כנראה", "amber"), "low": ("מוקדם לדעת", "gray")}
CONF_HELP = ("ההבדל מהממוצע: \"בטוח\" = הרבה משחקים והבדל ברור, \"כנראה\" = סביר, "
             "\"מוקדם לדעת\" = מעט משחקים או הבדל קטן, ואפשר שהוא מקרי.")


def _rows(rows, tone, show_moves=()):
    out = []
    for r in rows:
        label, ctone = CONF_HE[r.conf]
        moves = (f'<div class="moves" style="font-size:.78rem;line-height:1.5">{esc(last_plies(r.group))}</div>'
                 if r.opening in show_moves else "")
        out.append(
            f'<div class="orow"><div dir="ltr" style="text-align:right"><div class="nm">{esc(clip(r.opening, 34))}</div>'
            f'{moves}</div>'
            f'<div style="display:flex;align-items:center;gap:10px;white-space:nowrap">'
            f'<span class="pill {ctone}" title="{esc(CONF_HELP)}">{label}</span>'
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
    names = [r.opening for r in strong[:1]] + [r.opening for r in weak[:1]]
    same = {n for n in names if names.count(n) > 1}
    a, b = st.columns(2, gap="large")
    with a, st.container(border=True, key=f"card_strong_{c}", height="stretch"):
        md('<div class="plan-title" style="color:var(--green)">▲ חוזקות</div>'
           + (f'<div class="note">{snote}</div>' if snote else "") + _rows(strong[:1], "green", same))
    with b, st.container(border=True, key=f"card_weak_{c}", height="stretch"):
        md('<div class="plan-title" style="color:#dc2626">▼ חולשות</div>'
           + (f'<div class="note">{wnote}</div>' if wnote else "") + _rows(weak[:1], "red", same))


def _default_node(full, c):
    """The costliest opening with a repeated open mistake; else simply the costliest."""
    rep = [p for p in ctx.probs if p["color"] == c and p["count"] >= 2 and p["status"] != "learned"]
    order = full[full.cost > 0].sort_values("cost", ascending=False) if ctx.analyzed else full.iloc[0:0]
    for r in order.itertuples():
        ids = set(node_games(r).id)
        if any(ids & set(p["games"]) for p in rep):
            return r.key
    return order.key.iat[0] if len(order) else full.key.iat[0]


def select_node(key):
    st.session_state.op_key = key


def _tree_table(c):
    """The opening tree as rows: the name is a button spanning the row, the numbers sit beside it."""
    tbl = ctx.tbl
    full = tbl[tbl.color == c].reset_index(drop=True)
    show_all = bool(st.session_state.get("rp_all"))
    sel = st.session_state.get("op_key")
    if sel not in set(full.key):
        sel = _default_node(full, c)
    t = full if show_all or len(full) <= TREE_ROWS else full.head(TREE_ROWS)
    if sel not in set(t.key):
        t = pd.concat([t, full[full.key == sel]]).reset_index(drop=True)
    w = [6, 1.2]
    rows = st.container(key="tree_rows")
    head = rows.columns(w)
    for col, label in zip(head, ["פתיחה", "ציון"]):
        col.markdown(f'<span class="muted small">{label}</span>', unsafe_allow_html=True)
    labels = {r.key: clip(short_name(r), 30) for r in t.itertuples()}
    seen = {}
    for k_, v_ in labels.items():
        seen.setdefault(v_, []).append(k_)
    for r in t.itertuples():
        a, s_ = rows.columns(w, vertical_alignment="center")
        name = labels[r.key]
        if len(seen[name]) > 1:   # two rows with the same name: tell them apart by their last ply
            name = f"{name} · {last_plies(r.group, 1)}"
        label = ("┘ " if r.depth else "") + ltr_text(name) + ("  ⚠" if r.toxic else "")
        with a.container(key=f"opd{min(r.depth, 3)}_{c}_{r.key}"):
            st.button(label, key=f"op_{c}_{r.key}", on_click=select_node, args=(r.key,),
                      type="primary" if r.key == sel else "secondary", width="stretch")
        s_.markdown(f'<span class="small">{pct(r.score)}</span>', unsafe_allow_html=True)
    if len(full) > TREE_ROWS:
        st.toggle(f"הצג את כל הפתיחות ({len(full)})", key="rp_all")
    return full[full.key == sel].iloc[0]


def _node_mistakes(op):
    diff = (op.score - op.base) * 100
    with st.container(border=True, key="card_opening"):
        toxic = ' <span class="pill red">בעייתית</span>' if op.toxic else ""
        md(f'<div class="plan-title">{esc(he_title(op.opening))}{toxic}</div>'
           f'<div class="plan-en" dir="ltr" style="text-align:right">{esc(op.opening)}</div>')
        board, last = position_at(op.group.split(), int(op.plies))
        left, right = st.columns([1.35, 1], vertical_alignment="center")
        left.image(board_svg(board, op.color, last, [], size=150), width=150)
        with right:
            md(f'<div class="moves" style="font-size:.85rem">{esc(tail_moves(op.group, 24))}</div>'
               f'<div class="note"><b>{pct(op.score)}</b> ב־{op.games} משחקים, '
               f'<span dir="ltr">{diff:+.0f}%</span> מהממוצע {you("שלך", "של השחקן")} ב{COLORS[op.color]}.</div>')
        if ctx.me:
            st.button("לתרגל את הפתיחה ←", key=f"rp_practice_{op.key}", on_click=start_practice, args=(op.key,),
                      type="primary", width="stretch")
        if not ctx.analyzed:
            md('<div class="note" style="margin-top:12px">הטעויות עוד לא נותחו במנוע. אפשר להפעיל את הניתוח מההגדרות.</div>')
            return
        ids = set(node_games(op).id)
        found = sorted((p for p in ctx.probs if p["color"] == op.color and ids & set(p["games"])
                        and p["status"] != "learned"), key=lambda p: (-p["count"], -p["cost"]))
        repeated = [p for p in found if p["count"] >= 2]
        singles = len(found) - len(repeated)
        md(f'<div class="plan-title" style="margin-top:4px;font-size:.95rem">טעויות שחוזרות בפתיחה הזו ({len(repeated)})</div>')
        if not repeated:
            md('<div class="note">אין כאן טעויות שחוזרות ברגישות הנוכחית'
               + (f' ({singles} טעויות חד־פעמיות).' if singles else ".") + '</div>')
            return
        found = repeated
        top = found[0]
        txt, go = st.columns([2.6, 1.4], vertical_alignment="center")
        txt.markdown(f'<div class="plan-line"><b class="ltr">{esc(move_label(top["ply"], top["played"]))}</b> במקום '
                     f'<b class="ltr">{esc(move_label(top["ply"], top["best_san"] or "?"))}</b> · '
                     f'{in_games(top["mistakes"], top["reached"])}</div>', unsafe_allow_html=True)
        go.button("פתח ←", key=f"rp_open_{op.key}", on_click=open_mistake, args=(tr_key(top),), type="primary",
                  width="stretch")
        for i, p in enumerate(found[1:3], 1):
            a, b, c = st.columns([3, 1.8, 1.4], vertical_alignment="center")
            a.markdown(f'<span dir="ltr">{esc(move_label(p["ply"], p["played"]))}</span> ← '
                       f'<span dir="ltr">{esc(move_label(p["ply"], p["best_san"] or "?"))}</span>', unsafe_allow_html=True)
            tone = status_map()[p["status"]][1]
            b.markdown(f'<span class="small muted" title="{status_map()[p["status"]][0]}"><span style="color:var(--'
                       f'{ {"red": "red", "amber": "amber", "green": "green"}.get(tone, "soft") }">●</span> '
                       f'{p["count"]} פעמים</span>', unsafe_allow_html=True)
            c.button("פתח ←", key=f"rp_mk_{op.key}_{i}", on_click=open_mistake, args=(tr_key(p),), width="stretch")
        more = len(found) - 3
        if more > 0:
            st.caption(f"ועוד {more} שחוזרות. אפשר לראות את כולן במסך הטעויות.")


def _practice_screen(key):
    row = ctx.tbl[ctx.tbl.key == key]
    if row.empty:
        st.session_state.rp_drill = None
        st.rerun()
    op = row.iloc[0]
    st.button("→ חזרה לפתיחות", key="rp_back", on_click=stop_practice)
    md(f'<div class="plan-title">{esc(he_title(op.opening))}</div>'
       f'<div class="note">תרגול הפתיחה: מגיעים לעמדה אחרי <span class="ltr">{esc(tail_moves(op.group, 40))}</span>, '
       f'וממשיכים לשחק את הקו.</div>')
    drill(practice_position(op))


def page_repertoire():
    if st.session_state.get("rp_drill") and ctx.me:
        _practice_screen(st.session_state.rp_drill)
        return
    if ctx.tbl.empty:
        empty(f"אין פתיחה ששוחקה לפחות {C.MIN_GROUP_GAMES} פעמים בסינון הנוכחי.")
        return
    avail = [c for c in ctx.colors if not ctx.tbl[ctx.tbl.color == c].empty] or list(ctx.colors)
    head, pick_col = st.columns([3, 1.4], vertical_alignment="center")
    c = pick_col.segmented_control("צבע", avail, default=avail[0], key="rp_color", label_visibility="collapsed",
                                   format_func={"white": "○ לבן", "black": "● שחור"}.get, width="stretch")
    c = c if c in avail else avail[0]
    t = ctx.tbl[ctx.tbl.color == c]
    head.markdown(f'<h1 class="plan-h1" style="margin-top:0">{you("הפתיחות שלך", "הפתיחות של " + esc(ctx.user))}</h1>'
                  f'<p class="plan-sub">{you("איך אתה מצליח", "איך מצליח השחקן")} בכל פתיחה לעומת {you("הממוצע שלך", "הממוצע שלו")} ב{COLORS[c]}.</p>', unsafe_allow_html=True)
    _summary(c)
    st.caption("כל הפתיחות · לחצו על שם פתיחה כדי לראות את הטעויות בה")
    tcol, dcol = st.columns([1.5, 1], gap="large")
    with tcol:
        op = _tree_table(c)
    with dcol:
        _node_mistakes(op)
    if st.toggle("הצג גרף של כל הפתיחות", False, key=f"rp_chart_{c}"):
        st.altair_chart(weak_chart(ctx.tbl[ctx.tbl.color == c]), width="stretch")
