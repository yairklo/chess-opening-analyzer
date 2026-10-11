"""התוכנית שלי: the three things to fix this week, where points are lost, and progress."""
import chess
import streamlit as st

from chessapp import config as C

from .common import (CONF, GREEN, RED, WITH_COLOR, board_svg, chip, clip, en, empty, esc, md, move_label, pct,
                     status_map, tail_moves, you)
from .ctx import ctx
from .data import explain_p, recurring, start_analysis, tr_key
from .plan import PLAN_SIZE, focus_openings, plan_items, short_reason


def open_mistake(key):
    st.session_state.update(page="mistakes", mk_sel=key, mk_drill=True, quiz=False)


def open_opening(key):
    st.session_state.update(page="repertoire", op_key=key, quiz=False)


def go_repertoire():
    st.session_state.update(page="repertoire", quiz=False)


def start_quiz():
    st.session_state.quiz = True


def lower_sensitivity():
    st.session_state.thr = 8


def position_label(p):
    pre = p["pre_moves"]
    return f'אחרי <span class="ltr">{esc(move_label(p["ply"] - 1, pre[-1]))}</span>' if pre else "מעמדת הפתיחה"


def mistake_card(i, p):
    x = explain_p(p)
    with st.container(border=True, key=f"card_plan_{i}", height="stretch"):
        a, b = st.columns([1, 1.5], vertical_alignment="center")
        a.image(board_svg(chess.Board(p["fen"]), p["color"], None,
                          [(p["played_uci"], RED), (p["best_uci"], GREEN)], size=150), width=150)
        with b:
            md(f'<div class="card-h"><span class="rank">{i + 1}</span>{chip(p["color"])}</div>'
               f'<div class="card-h"><span class="t">{en(clip(p["opening"], 28))}</span></div>'
               f'<div class="plan-pos">{position_label(p)}</div>')
        md(f'<div class="plan-text">{you("שיחקת", "שוחק")} <span class="ltr">{esc(move_label(p["ply"], p["played"]))}</span> '
           f'ב‑{p["mistakes"]} מתוך {p["reached"]} משחקים. עדיף <span class="ltr">{esc(move_label(p["ply"], p["best_san"] or "?"))}</span>.</div>'
           f'<div class="plan-why">{esc(short_reason(x["why"]))}</div>')
        st.button("לתקן עכשיו ←", key=f"fix_{i}", on_click=open_mistake, args=(tr_key(p),), type="primary",
                  width="stretch")


def opening_card(i, r):
    with st.container(border=True, key=f"card_plan_{i}", height="stretch"):
        md(f'<div class="card-h"><span class="rank">{i + 1}</span>{chip(r.color)}'
           f'<span class="badge b-amber">פתיחה חלשה</span></div>'
           f'<div class="card-h"><span class="t">{en(clip(r.opening, 30))}</span></div>'
           f'<div class="moves">{esc(tail_moves(r.group, 30))}</div>'
           f'<div class="plan-text">התוצאות כאן נמוכות מהממוצע שלך: {pct(r.score)} לעומת {pct(r.base)}.</div>')
        st.button("לפתיחה ←", key=f"open_{i}", on_click=open_opening, args=(r.key,), width="stretch")


def where_points_go():
    top = focus_openings(3)
    with st.container(border=True, key="card_focus"):
        md('<div class="card-h"><span class="t">איפה אתה מפסיד נקודות</span></div>')
        if top.empty:
            md(f'<div class="note">{you("אין פתיחה שמורידה את הממוצע שלך. יפה!", "אין פתיחה שמורידה את הממוצע באופן בולט.")}</div>')
        for r in top.itertuples():
            pill = (f'<span class="badge b-{CONF[r.conf][1]}" title="ההבדל מהממוצע קטן או מבוסס על מעט משחקים">'
                    f'{CONF[r.conf][0]}</span>' if r.conf == "low" else "")
            md(f'<div class="orow"><div><div class="nm">{en(clip(r.opening, 30))} {pill}</div>'
               f'<div class="moves" style="font-size:.8rem;line-height:1.5">{esc(tail_moves(r.group, 30))}</div></div>'
               f'<div class="sc">{pct(r.score)}</div></div>')
        st.button("לכל הרפרטואר", key="to_repertoire", on_click=go_repertoire, width="stretch")


def progress_card():
    rec = recurring(ctx.probs) if ctx.analyzed else []
    counts = {s: sum(p["status"] == s for p in rec) for s in ("repeating", "improving", "learned")}
    total = sum(counts.values())
    with st.container(border=True, key="card_progress"):
        md('<div class="card-h"><span class="t">ההתקדמות שלך</span></div>')
        if not total:
            md('<div class="note">עוד אין טעויות חוזרות שאפשר לעקוב אחריהן.</div>')
            return
        w = {k: v / total * 100 for k, v in counts.items()}
        md(f'<div class="stats s3"><div><div class="k">עדיין חוזרות</div><div class="v" style="color:var(--red)">{counts["repeating"]}</div></div>'
           f'<div><div class="k">בדרך לתיקון</div><div class="v">{counts["improving"]}</div></div>'
           f'<div><div class="k">נלמדו</div><div class="v" style="color:var(--green)">{counts["learned"]}</div></div></div>'
           f'<div class="prog"><span class="l" style="width:{w["learned"]:.0f}%"></span>'
           f'<span class="i" style="width:{w["improving"]:.0f}%"></span><span class="r" style="width:{w["repeating"]:.0f}%"></span></div>'
           f'<div class="note">{status_map()["learned"][2]}</div>')


def page_home():
    md('<h1 class="plan-h1">3 דברים לתקן השבוע</h1>'
       '<p class="plan-sub">נבחרו לפי כמה נקודות הם עולים לך. כל אחד לוקח בערך 5 דקות.</p>')
    if not ctx.analyzed:
        st.caption("הטעויות עוד לא נותחו במנוע, ולכן מוצגות רק פתיחות חלשות. אפשר להפעיל את הניתוח מההגדרות (⚙).")
        st.button("נתח את הטעויות עכשיו", key="home_analyze", on_click=start_analysis, args=(ctx.user,),
                  icon=":material/memory:")
    with st.spinner("בוחר את התוכנית..."):
        picks = plan_items()
    if not picks:
        empty("אין טעויות שחוזרות בסף הנוכחי, וגם אין פתיחה חלשה בולטת.<br>אפשר להפחית את הרגישות ולראות גם אי־דיוקים.")
        st.button("להפחית את הרגישות ←", key="lower_sens", on_click=lower_sensitivity, type="primary")
    else:
        cols = st.columns(PLAN_SIZE)
        for i, (col, (kind, item)) in enumerate(zip(cols, picks)):
            with col:
                (mistake_card if kind == "mistake" else opening_card)(i, item)
        if sum(k == "mistake" for k, _ in picks) < len(picks):
            st.caption("חסרות טעויות חוזרות, ולכן הושלמו פתיחות חלשות.")
    st.markdown("")
    a, b = st.columns(2, gap="large")
    with a:
        where_points_go()
    with b:
        progress_card()
    if ctx.me and ctx.analyzed:
        st.button("תרגול מהיר: חידון של 2 דקות על כל הטעויות", key="to_quiz", on_click=start_quiz,
                  icon=":material/quiz:")
