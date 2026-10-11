"""טעויות: one mistake at a time, board first. Details are tucked into expanders; the line trainer opens inline."""
import chess
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.lines import study_pgn

from .common import (GREEN, LRM, RED, arrow_legend, badge, board_svg, chip, empty, en, esc, explorer_html, fmt_date,
                     game_links, line_html, md, move_label, pct, rtl_table, set_state, status_map, you)
from .ctx import ctx
from .data import (by_cost, explain_p, find_mistake, level_html, level_view, list_mistakes, start_analysis, tr_key)
from .trainer import drill


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



def line_board(p, x):
    """The card's board: the mistake with arrows, or the correct line / the punishment played out move by move."""
    k = f'lb_{abs(hash((p["color"], p["key"], p["played"])))}'
    mode = st.segmented_control("על הלוח", ["mistake", "better", "punish"], default="mistake", key=f"{k}_mode",
                                format_func={"mistake": "הטעות", "better": "הקו הנכון", "punish": "קו העונש"}.get,
                                label_visibility="collapsed", width="stretch")
    before = chess.Board(p["fen"])
    if mode not in ("better", "punish"):
        st.image(board_svg(before, p["color"], None, [(p["played_uci"], RED), (p["best_uci"], GREEN)], size=420), width=420)
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
    st.image(board_svg(b, p["color"], last, size=420), width=420)
    c = st.columns(4)
    c[0].button("התחלה", key=f"{pk}_s", on_click=set_state, args=(pk, 0), disabled=cur == 0, width="stretch")
    c[1].button("הקודם", key=f"{pk}_p", on_click=set_state, args=(pk, max(0, cur - 1)), disabled=cur == 0, width="stretch")
    c[2].button("הבא", key=f"{pk}_n", on_click=set_state, args=(pk, min(len(sans), cur + 1)),
                disabled=cur >= len(sans), width="stretch")
    c[3].button("סוף", key=f"{pk}_e", on_click=set_state, args=(pk, len(sans)), disabled=cur >= len(sans), width="stretch")
    intro = ("הקו של המנוע אחרי המסע הנכון:" if mode == "better"
             else f'מה קורה אחרי {move_label(p["ply"], p["played"])}, לפי המנוע:')
    md(f'<div class="note" style="margin-top:6px">{intro}</div>' + line_html(sans, first_ply, cur))


def select(key):
    st.session_state.update(mk_sel=key, mk_drill=False)


def start_drill():
    st.session_state.mk_drill = True


def stop_drill():
    st.session_state.mk_drill = False


def lower_sensitivity():
    st.session_state.thr = 8


def _items():
    """Mistakes to walk through: repeated ones (2+ games), or all of them when asked; the selected one is always in."""
    items = by_cost(ctx.probs) if st.session_state.get("mk_all") else list_mistakes()
    sel = st.session_state.get("mk_sel")
    if sel and not any(tr_key(p) == sel for p in items):
        p = find_mistake(sel)
        if p:
            items = [p] + items
    return items


def _top_bar(items, idx):
    a, b, c = st.columns([3, 1, 1], vertical_alignment="center")
    a.markdown(f"**{idx + 1} מתוך {len(items)}**")
    keys = [tr_key(p) for p in items]
    b.button("‹ הקודמת", key="mk_prev", on_click=select, args=(keys[max(idx - 1, 0)],), disabled=idx == 0, width="stretch")
    c.button("הבאה ›", key="mk_next", on_click=select, args=(keys[min(idx + 1, len(items) - 1)],),
             disabled=idx >= len(items) - 1, width="stretch")


def _all_mistakes(items, idx):
    with st.expander(f"כל הטעויות ({len(items)})"):
        st.checkbox("להציג גם טעויות שקרו פעם אחת", key="mk_all")
        view = pd.DataFrame({
            "פתיחה": [p["opening"] for p in items],
            you("שיחקת", "שוחק"): [LRM + move_label(p["ply"], p["played"]) + LRM for p in items],
            "עדיף": [LRM + move_label(p["ply"], p["best_san"] or "?") + LRM for p in items],
            "פעמים": [p["count"] for p in items], "מצב": [status_map()[p["status"]][0] for p in items]})
        ev = rtl_table(view, on_select="rerun", selection_mode="single-row",
                       key=f"mk_tbl_{tr_key(items[idx])}_{len(items)}", height=min(38 + 35 * len(items), 300))
        if ev.selection.rows:
            chosen = tr_key(items[ev.selection.rows[0]])
            if chosen != tr_key(items[idx]):
                select(chosen)
                st.rerun()
        export = items[:60]
        pgn_key = f"pgn_{ctx.user}_{ctx.thr}_{hash(tuple(tr_key(p) for p in export))}"
        if pgn_key in st.session_state:
            st.download_button("הורדת קובץ PGN ל־Lichess Study", st.session_state[pgn_key],
                               file_name=f"opening-mistakes-{ctx.user}.pgn", mime="application/x-chess-pgn",
                               icon=":material/download:", key="pgn_dl")
        elif st.button(f"הכנת PGN ל־Lichess Study ({len(export)} עמדות)", icon=":material/description:", key="pgn_make"):
            with st.spinner("מחשב קווים במנוע לכל עמדה..."):
                st.session_state[pgn_key] = study_pgn(export)
            st.rerun()


def _details(p, x, lv):
    with st.expander(f"מה קרה במשחקים שלך ({p['count']})"):
        md(f'<div class="stats s3"><div><div class="k">{you("חזרת על הטעות", "חזרות על הטעות")}</div>'
           f'<div class="v">{p["mistakes"]} מתוך {p["reached"]}</div></div>'
           f'<div><div class="k">הציון במשחקים האלה</div><div class="v">{pct(p["score"])}</div></div>'
           f'<div><div class="k">הממוצע בצבע</div><div class="v">{pct(p["avg"])}</div></div></div>'
           f'<div class="note">{cost_note(p)}</div>'
           f'{replies_html(p, x["punish_first"])}'
           f'<div class="note" style="margin-top:10px">{usual_html(p)}</div>'
           f'<div class="note" style="margin-top:10px">המשחקים:</div>{game_links(p["games"], p["color"], p["ply"])}')
    with st.expander("מה משחקים ברמה שלך"):
        if lv and lv.get("ex"):
            md(level_html(p, lv) + explorer_html(lv["ex"], p["color"]))
        elif lv:
            st.caption(f"Opening Explorer לא זמין כרגע: {lv['error']}.")
        else:
            st.caption("כדי לראות מה משחקים שחקנים ברמה דומה צריך טוקן אישי של Lichess (ראו README).")
    with st.expander("עוד"):
        cost = p["cost"]
        cost_txt = (f'<span style="color:var(--red)">−{cost:.1f}</span>' if cost > 0.05 else
                    f'<span style="color:var(--green)">+{-cost:.1f}</span>' if cost < -0.05 else "0")
        md(f'<div class="stats"><div><div class="k">סיכויי ניצחון</div><div class="v">{p["win_before"]:.0f}% ← {p["win_after"]:.0f}%</div></div>'
           f'<div><div class="k">{"מחיר בנקודות" if cost >= -0.05 else "בפועל: רווח בנקודות"}</div><div class="v"><span dir="ltr">{cost_txt}</span></div></div>'
           f'<div><div class="k">פעם אחרונה</div><div class="v">{fmt_date(p["last_mistake"]) if p["last_mistake"] else "—"}</div></div></div>'
           f'<div class="note">{status_map()[p["status"]][2]}</div>'
           f'<div class="lines"><span class="k">העונש (מנוע):</span><span class="ltr">{esc(x["punish"]) or "—"}</span>'
           f'<span class="k">הקו הנכון:</span><span class="ltr">{esc(x["better"]) or "—"}</span></div>'
           f'<div class="note"><a href="{x["url"]}" target="_blank">פתיחת העמדה בלוח הניתוח של Lichess ↗</a></div>')


def page_mistakes():
    if not ctx.analyzed:
        empty("הטעויות עוד לא נותחו במנוע.<br>אפשר להפעיל את הניתוח מההגדרות (⚙).")
        st.button("נתח את הטעויות עכשיו", key="mk_analyze", on_click=start_analysis, args=(ctx.user,),
                  icon=":material/memory:", type="primary")
        return
    items = _items()
    if not items:
        empty("אין טעויות שחוזרות בסף הנוכחי.<br>אפשר להפחית את הרגישות, או לראות גם טעויות שקרו פעם אחת.")
        a, b = st.columns(2)
        a.button("להפחית את הרגישות ←", key="mk_lower", on_click=lower_sensitivity, type="primary", width="stretch")
        b.checkbox("להציג גם טעויות שקרו פעם אחת", key="mk_all")
        return
    keys = [tr_key(p) for p in items]
    sel = st.session_state.get("mk_sel")
    idx = keys.index(sel) if sel in keys else 0
    st.session_state.mk_sel = keys[idx]
    p = items[idx]
    _top_bar(items, idx)
    _all_mistakes(items, idx)
    if st.session_state.get("mk_drill") and ctx.me:
        st.button("→ חזרה לטעות", key="mk_back", on_click=stop_drill)
        md(f'<div class="card-h">{chip(p["color"])}<span class="t">{en(p["opening"])}</span></div>')
        drill(p)
        return

    x = explain_p(p)
    lv = level_view(p)
    works = bool(lv and lv.get("works"))
    a, b = st.columns([1.1, 1], gap="large")
    with a:
        line_board(p, x)
    with b:
        level_badge = f'<span class="badge b-blue">עובד ברמה {you("שלך", "הזו")}</span>' if works else ""
        md(f'<div class="card-h">{chip(p["color"])}{badge(p["status"])}{level_badge}</div>'
           f'<div class="card-h"><span class="t">{en(p["opening"])}</span></div>'
           f'<div class="mk-h1"><bdi dir="ltr">{esc(move_label(p["ply"], p["played"]))}?</bdi> → '
           f'<bdi dir="ltr">{esc(move_label(p["ply"], p["best_san"] or "?"))}</bdi></div>'
           f'<div class="cmp"><div class="bad"><div class="k">{you("שיחקת", "שוחק")}</div>'
           f'<div class="v">{esc(move_label(p["ply"], p["played"]))}</div></div>'
           f'<div class="good"><div class="k">עדיף</div><div class="v">{esc(move_label(p["ply"], p["best_san"] or "?"))}</div></div></div>'
           f'<div class="why"><b>למה:</b> {esc(x["why"])}</div>')
        if ctx.me:
            st.button(f"התאמן על הקו ({C.TRAIN_DEFAULT_MOVES} מסעים ומעלה) ←", key="mk_drill_btn", on_click=start_drill,
                      type="primary", width="stretch")
    _details(p, x, lv)
