"""התוכנית שלי: what to fix this week, where points are lost, and progress."""
import chess
import streamlit as st

from chessapp import config as C

from .common import COLORS, GREEN, RED, bidi, board_svg, in_games, clip, empty, esc, md, move_label, pct, tail_moves, you
from .ctx import ctx
from .data import explain_p, recurring, start_analysis, tr_key
from .names import en_sub, he_title
from .plan import PLAN_SIZE, focus_openings, plan_items, short_reason


def open_mistake(key):
    st.session_state.update(page="mistakes", mk_sel=key, mk_drill=True, quiz=False)


def open_opening(key):
    st.session_state.update(page="repertoire", op_key=key, quiz=False, rp_all=False,
                            op_nonce=st.session_state.get("op_nonce", 0) + 1)


def go_repertoire():
    st.session_state.update(page="repertoire", quiz=False)


def start_quiz():
    st.session_state.quiz = True


def lower_sensitivity():
    st.session_state.thr = 8


def position_label(p):
    pre = p["pre_moves"]
    return f'אחרי <span class="ltr">{esc(move_label(p["ply"] - 1, pre[-1]))}</span>' if pre else "מעמדת הפתיחה"


def card_head(i, title, sub):
    return (f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'
            f'<div><div class="plan-title">{esc(title)}</div><div class="plan-en">{esc(sub)}</div></div>'
            f'<span class="rank">{i + 1}</span></div>')


def mistake_card(i, p):
    x = explain_p(p)
    with st.container(border=True, key=f"card_plan_{i}", height="stretch"):
        md(card_head(i, he_title(p["opening"]), en_sub(p["opening"], COLORS[p["color"]])))
        pad, mid, pad2 = st.columns([1, 4, 1])
        mid.image(board_svg(chess.Board(p["fen"]), p["color"], None,
                            [(p["played_uci"], RED), (p["best_uci"], GREEN)], size=240), width=240)
        md(f'<div class="plan-line">{you("שיחקת", "שוחק")} <b class="ltr">{esc(move_label(p["ply"], p["played"]))}</b> '
           f'{in_games(p["mistakes"], p["reached"])}</div>'
           f'<div class="plan-line">עדיף <b class="ltr">{esc(move_label(p["ply"], p["best_san"] or "?"))}</b></div>'
           f'<div class="plan-reason">{bidi(x.get("why_short") or short_reason(x["why"], 16))}</div>')
        st.button("לתקן עכשיו ←", key=f"fix_{i}", on_click=open_mistake, args=(tr_key(p),), type="primary",
                  width="stretch")


def opening_card(i, r):
    with st.container(border=True, key=f"card_plan_{i}", height="stretch"):
        md(card_head(i, he_title(r.opening), en_sub(r.opening, COLORS[r.color])))
        md(f'<div style="margin:8px 0"><span class="pill amber">פתיחה חלשה</span></div>'
           f'<div class="moves">{esc(tail_moves(r.group, 30))}</div>'
           f'<div class="plan-reason">התוצאות כאן נמוכות מהממוצע {you("שלך", "של השחקן")}: {pct(r.score)} לעומת {pct(r.base)}.</div>')
        st.button("לפתיחה ←", key=f"open_{i}", on_click=open_opening, args=(r.key,), width="stretch")


def where_points_go():
    top = focus_openings(3)
    with st.container(border=True, key="card_focus"):
        h, link = st.columns([3, 1.6], vertical_alignment="center")
        h.markdown('<div class="plan-title">איפה מפסידים נקודות</div>', unsafe_allow_html=True)
        link.button("לכל הפתיחות ←", key="to_repertoire", on_click=go_repertoire, type="tertiary")
        if top.empty:
            md(f'<div class="note">{you("אין פתיחה שמורידה את הממוצע שלך. יפה!", "אין פתיחה שמורידה את הממוצע באופן בולט.")}</div>')
        for k, r in enumerate(top.itertuples()):
            a, b, c, d = st.columns([4.2, 1, 1.9, 1.5], vertical_alignment="center")
            a.markdown(f'<div class="nm" dir="ltr" style="text-align:right;font-weight:600">{esc(clip(r.opening, 30))}'
                       f' <span class="muted small" style="font-weight:400">{esc(tail_moves(r.group, 24))}</span></div>',
                       unsafe_allow_html=True)
            b.markdown(f'<span class="muted small">{COLORS[r.color]}</span>', unsafe_allow_html=True)
            c.markdown(f'<span style="color:var(--accent);font-weight:700">{pct(r.score)}</span> '
                       f'<span class="muted small">מול {pct(r.base)}</span>', unsafe_allow_html=True)
            d.button("לטעויות ←", key=f"focus_{k}", on_click=open_opening, args=(r.key,), type="tertiary")


def progress_card():
    rec = recurring(ctx.probs) if ctx.analyzed else []
    counts = {s: sum(p["status"] == s for p in rec) for s in ("repeating", "improving", "learned")}
    total = sum(counts.values())
    with st.container(border=True, key="card_progress"):
        md(f'<div class="plan-title">ההתקדמות {you("שלך", "של השחקן")}</div>')
        if not total:
            md('<div class="note">עוד אין טעויות חוזרות שאפשר לעקוב אחריהן.</div>')
            return
        w = {k: v / total * 100 for k, v in counts.items()}
        md(f'<div class="prog"><span class="r" style="width:{w["repeating"]:.0f}%"></span>'
           f'<span class="i" style="width:{w["improving"]:.0f}%"></span><span class="l" style="width:{w["learned"]:.0f}%"></span></div>'
           f'<div class="legend"><span><i style="background:#ef4444"></i>חוזרות {counts["repeating"]}</span>'
           f'<span><i style="background:#f59e0b"></i>בדרך לתיקון {counts["improving"]}</span>'
           f'<span><i style="background:#22c55e"></i>נלמדו {counts["learned"]}</span></div>'
           f'<div class="note">טעות נחשבת "נלמדה" כשמשחקים אותה {C.LEARN_FIXED_AFTER} פעמים ברצף במשחקים אמיתיים.</div>')


def page_home():
    if ctx.analyzed:
        sub_txt = (f"שלוש הטעויות שחוזרות {you('אצלך', 'אצל ' + esc(ctx.user))} ועולות "
                   f"{you('לך', 'לו')} הכי הרבה נקודות. כל אחת לוקחת בערך 5 דקות.")
    else:
        sub_txt = (f"הפתיחות שעולות {you('לך', 'עבור ' + esc(ctx.user))} הכי הרבה נקודות. "
                   "הטעויות עוד לא נותחו במנוע.")
    md(f'<h1 class="plan-h1">מה לתקן השבוע</h1><p class="plan-sub">{sub_txt}</p>')
    if not ctx.analyzed:
        st.caption("הטעויות עוד לא נותחו במנוע, ולכן מוצגות רק פתיחות חלשות. אפשר להפעיל את הניתוח מההגדרות (⚙).")
        st.button("נתח את הטעויות עכשיו", key="home_analyze", on_click=start_analysis, args=(ctx.user,),
                  icon=":material/memory:")
    with st.spinner("בוחר את התוכנית..."):
        picks = plan_items()
    if not picks:
        empty("אין טעויות שחוזרות ברגישות הנוכחית, וגם אין פתיחה חלשה בולטת.<br>אפשר להפחית את הרגישות ולראות גם אי־דיוקים.")
        st.button("להפחית את הרגישות ←", key="lower_sens", on_click=lower_sensitivity, type="primary")
    else:
        cols = st.columns(PLAN_SIZE)
        for i, (col, (kind, item)) in enumerate(zip(cols, picks)):
            with col:
                (mistake_card if kind == "mistake" else opening_card)(i, item)
        if sum(k == "mistake" for k, _ in picks) < len(picks):
            st.caption("חסרות טעויות חוזרות, ולכן הושלמו פתיחות חלשות.")
    st.markdown("")
    a, b = st.columns([1.5, 1], gap="large")
    with a:
        where_points_go()
    with b:
        progress_card()
    if ctx.me and ctx.analyzed:
        st.button("תרגול מהיר: חידון של 2 דקות על כל הטעויות", key="to_quiz", on_click=start_quiz,
                  icon=":material/quiz:")
