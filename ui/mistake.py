"""טעויות: one mistake at a time, board first. Details are tucked into expanders; the line trainer opens inline."""
import chess
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.lines import study_pgn

from .names import en_sub
from .common import (COLORS, GREEN, LRM, RED, RESULTS, moves_html, position_at, arrow_legend, badge, board_svg, chip, empty, en, esc, explorer_html, fmt_date,
                     game_links, line_html, md, move_label, pct, rtl_table, set_state, status_map, you)
from .ctx import ctx
from .data import explain_p, find_mistake, level_html, level_view, start_analysis, tr_key
from .plan import ordered_mistakes
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
    """The board: the mistake with arrows, or the correct line / the punishment played out move by move."""
    k = f'lb_{abs(hash((p["color"], p["key"], p["played"])))}'
    mode = st.session_state.get(f"{k}_mode") or "mistake"
    before = chess.Board(p["fen"])
    sans, first_ply, cur, pk = [], p["ply"], 0, None
    if mode == "better":
        start, sans, first_ply = before, x.get("better_sans") or [], p["ply"]
    elif mode == "punish":
        start = before.copy()
        start.push(chess.Move.from_uci(p["played_uci"]))
        sans, first_ply = x.get("punish_sans") or [], p["ply"] + 1
    with st.container(border=True, key=f"card_board_{k}"):
        if mode == "mistake" or not sans:
            st.image(board_svg(before, p["color"], None, [(p["played_uci"], RED), (p["best_uci"], GREEN)], size=420), width=420)
            if mode != "mistake":
                st.caption("אין קו להצגה בעמדה הזו.")
        else:
            pk = f"{k}_{mode}_ply"
            st.session_state.setdefault(pk, 1)
            cur = min(st.session_state[pk], len(sans))
            b, last = start.copy(), None
            for san in sans[:cur]:
                last = b.push_san(san)
            st.image(board_svg(b, p["color"], last, size=380), width=380)
            c = st.columns(4)
            c[0].button("»", key=f"{pk}_s", on_click=set_state, args=(pk, 0), disabled=cur == 0, width="stretch",
                        help="להתחלה")
            c[1].button("›", key=f"{pk}_p", on_click=set_state, args=(pk, max(0, cur - 1)), disabled=cur == 0,
                        width="stretch", help="אחורה")
            c[2].button("‹", key=f"{pk}_n", on_click=set_state, args=(pk, min(len(sans), cur + 1)),
                        disabled=cur >= len(sans), width="stretch", help="קדימה")
            c[3].button("«", key=f"{pk}_e", on_click=set_state, args=(pk, len(sans)), disabled=cur >= len(sans),
                        width="stretch", help="לסוף")
        st.segmented_control("על הלוח", ["mistake", "better", "punish"], default="mistake", key=f"{k}_mode",
                             format_func={"mistake": "הטעות", "better": "הקו הנכון", "punish": "העונש"}.get,
                             label_visibility="collapsed", width="stretch")
        if mode == "mistake":
            md(arrow_legend())
        elif sans:
            intro = ("הקו של המנוע אחרי המסע הנכון:" if mode == "better"
                     else f'מה קורה אחרי <bdi dir="ltr">{esc(move_label(p["ply"], p["played"]))}</bdi>, לפי המנוע:')
            md(f'<div class="note" style="margin-top:6px">{intro}</div>'
               f'<div style="overflow-x:auto;white-space:nowrap">{line_html(sans, first_ply, cur)}</div>')


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
    base = ctx.probs if st.session_state.get("mk_all") else [p for p in ctx.probs if p["count"] >= 2]
    items = ordered_mistakes(base)
    sel = st.session_state.get("mk_sel")
    if sel and not any(tr_key(p) == sel for p in items):
        p = find_mistake(sel)
        if p:
            items = [p] + items
    return items


def _top_bar(items, idx, drilling=False):
    keys = [tr_key(p) for p in items]
    a, b, back, c = st.columns([2.2, 1.6, 1.8 if drilling else 0.01, 3.4], vertical_alignment="center")
    if drilling:
        back.button("→ חזרה לטעות", key="mk_back", on_click=stop_drill)
    a.markdown(f'<span class="mk-crumb">טעות</span> **{idx + 1} מתוך {len(items)}**', unsafe_allow_html=True)
    with b:
        x, y = st.columns(2)
        x.button("›", key="mk_prev", on_click=select, args=(keys[max(idx - 1, 0)],), disabled=idx == 0, width="stretch",
                 help="הטעות הקודמת")
        y.button("‹", key="mk_next", on_click=select, args=(keys[min(idx + 1, len(items) - 1)],),
                 disabled=idx >= len(items) - 1, width="stretch", help="הטעות הבאה")
    return c


def _all_mistakes(items, idx, where):
    with where.expander(f"כל הטעויות ({len(items)})"):
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


def _game_viewer(p):
    """Pick one of the games and step through it up to the mistake."""
    games = ctx.fdf[ctx.fdf.id.isin(p["games"])].sort_values("created", ascending=False)
    if games.empty:
        return
    label = {r.id: f"{fmt_date(r.created)} · {RESULTS[r.result]}" for r in games.itertuples()}
    gid = st.selectbox("משחק", list(label), format_func=label.get, key=f"gv_game_{tr_key(p)}")
    moves = games[games.id == gid].moves.iat[0].split()
    last = min(p["ply"] - 1, len(moves))
    ply = st.slider("מסע", 0, last, last, key=f"gv_ply_{tr_key(p)}_{gid}",
                    help="גוררים כדי לעבור על המשחק עד הרגע שבו טעית")
    board, lastmove = position_at(moves, ply)
    at_mistake = ply == p["ply"] - 1
    st.image(board_svg(board, p["color"], lastmove, [(p["played_uci"], RED)] if at_mistake else [], size=340), width=340)
    md(moves_html(moves[:last], cur=ply or None))


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
        _game_viewer(p)
    with st.expander("מה משחקים ברמה שלך"):
        if lv and lv.get("ex"):
            md(level_html(p, lv) + explorer_html(lv["ex"], p["color"]))
        elif lv:
            st.caption(f"Opening Explorer לא זמין כרגע: {lv['error']}.")
        else:
            st.caption("כדי לראות מה משחקים שחקנים ברמה דומה צריך טוקן אישי של Lichess (ראו README).")
    with st.expander("עוד: אחוזים, עלות, PGN, Lichess"):
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
        empty("אין טעויות שחוזרות ברגישות הנוכחית.<br>אפשר להפחית את הרגישות, או לראות גם טעויות שקרו פעם אחת.")
        a, b = st.columns(2)
        a.button("להפחית את הרגישות ←", key="mk_lower", on_click=lower_sensitivity, type="primary", width="stretch")
        b.checkbox("להציג גם טעויות שקרו פעם אחת", key="mk_all")
        return
    keys = [tr_key(p) for p in items]
    sel = st.session_state.get("mk_sel")
    idx = keys.index(sel) if sel in keys else 0
    st.session_state.mk_sel = keys[idx]
    p = items[idx]
    drilling = bool(st.session_state.get("mk_drill") and ctx.me)
    where = _top_bar(items, idx, drilling)
    _all_mistakes(items, idx, where)
    if drilling:
        drill(p)
        return

    x = explain_p(p)
    lv = level_view(p)
    works = bool(lv and lv.get("works"))
    tone = status_map()[p["status"]][1]
    played_lbl = esc(move_label(p["ply"], p["played"]))
    best_lbl = esc(move_label(p["ply"], p["best_san"] or "?"))
    text, board_col = st.columns([1, 1.05], gap="large")
    with text:
        level_badge = f' <span class="pill blue">עובד ברמה {you("שלך", "הזו")}</span>' if works else ""
        md(f'<div><span class="pill {tone}">{status_map()[p["status"]][0]}</span>{level_badge}'
           f' <span class="mk-sub">{esc(en_sub(p["opening"], COLORS[p["color"]]))}</span></div>'
           f'<div class="mk-h1"><bdi dir="ltr">{played_lbl}?</bdi><span class="arrow-sep">←</span><bdi dir="ltr">{best_lbl}</bdi></div>'
           f'<div class="cmp"><div class="bad"><div class="k">{you("שיחקת", "שוחק")}</div><div class="v">{played_lbl}</div>'
           f'<div class="s">ב־{p["mistakes"]} מתוך {p["reached"]} משחקים</div></div>'
           f'<div class="good"><div class="k">עדיף</div><div class="v">{best_lbl}</div>'
           f'<div class="s">המסע של המנוע</div></div></div>'
           f'<div class="why"><b>למה זו טעות:</b> {esc(x["why"])}</div>')
        if ctx.me:
            st.button("התאמן על הקו ←", key="mk_drill_btn", on_click=start_drill, type="primary", width="stretch")
        _details(p, x, lv)
    with board_col:
        line_board(p, x)
