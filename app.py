import random

import chess
import chess.svg
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.stats import load_results, occurrences, opening_table, overall, problem_positions, san_of

st.set_page_config(page_title="ניתוח פתיחות – yairklo", layout="wide")
st.markdown("""
<style>
.stApp, .block-container, [data-testid="stSidebar"] {direction: rtl; text-align: right;}
[data-testid="stDataFrame"], [data-testid="stMetric"] {direction: rtl;}
.ltr {direction: ltr; unicode-bidi: embed; display: inline-block; font-family: monospace;}
</style>""", unsafe_allow_html=True)

SPEEDS = {"bullet": "בוליט", "blitz": "בליץ", "rapid": "רפיד", "classical": "קלאסי"}
COLORS = {"white": "לבן", "black": "שחור"}
LEARNED = "נלמד ✅"
RESULTS = {"win": "ניצחון", "draw": "תיקו", "loss": "הפסד"}


@st.cache_data(show_spinner="טוען נתונים...")
def get_data():
    return load_results()


@st.cache_data(show_spinner="מחשב היסטוריית עמדות...")
def get_occ():
    return occurrences(get_data())


@st.cache_data(show_spinner="מחשב המלצות...")
def get_problems(color, sort, top=C.TOP_POSITIONS, hide_learned=True):
    ps = problem_positions(get_data(), color, top=None, with_explorer=False, sort=sort, occ=get_occ())
    if hide_learned:
        ps = [p for p in ps if p["status"] != LEARNED]
    ps = ps[:top]
    if C.LICHESS_TOKEN:
        from chessapp.explorer import lookup
        rating = int(get_data().query("color == @color").rating.median())
        for p in ps:
            p["explorer"] = lookup(p["fen"], rating)
    return ps


def ltr(t):
    return f'<span class="ltr">{t}</span>'


def pct(x):
    return f"{x:.0%}"


try:
    df = get_data()
except Exception:
    st.error("לא נמצאו תוצאות ניתוח. הריצו קודם: python run_all.py")
    st.stop()

st.title(f"ניתוח פתיחות – {C.USER}")

with st.sidebar:
    st.header("סינון")
    colors = st.multiselect("צבע", list(COLORS), list(COLORS), format_func=COLORS.get)
    avail = [s for s in SPEEDS if s in set(df.speed)] + sorted(set(df.speed) - set(SPEEDS))
    speeds = st.multiselect("קצב משחק", avail, avail, format_func=lambda s: SPEEDS.get(s, s))
fdf = df[df.color.isin(colors) & df.speed.isin(speeds)]
base = fdf.score.mean() if len(fdf) else 0.0

tab_sum, tab_tbl, tab_tox, tab_rec, tab_board = st.tabs(
    ["סיכום כללי", "טבלת פתיחות", "פתיחות רעילות", "עמדות בעייתיות והמלצות", "לוח ותרגול"])

with tab_sum:
    if len(fdf):
        o = overall(fdf)
        c = st.columns(5)
        c[0].metric("משחקים שנותחו", o["games"])
        c[1].metric("ציון ממוצע", f"{o['score']:.1%}")
        c[2].metric("ניצחון / תיקו / הפסד", f"{o['win']:.0%} / {o['draw']:.0%} / {o['loss']:.0%}")
        c[3].metric("משחקים עם שגיאה ראשונה", o["games_with_error"])
        c[4].metric("מסע ממוצע של שגיאה ראשונה", f"{o['avg_first_error_move']:.1f}")
    rows = []
    for col in COLORS:
        for sp in avail:
            s = fdf[(fdf.color == col) & (fdf.speed == sp)]
            if len(s):
                rows.append({"צבע": COLORS[col], "קצב": SPEEDS.get(sp, sp), "משחקים": len(s),
                             "ניצחון": pct((s.result == "win").mean()), "תיקו": pct((s.result == "draw").mean()),
                             "הפסד": pct((s.result == "loss").mean()), "ציון": f"{s.score.mean():.1%}",
                             "מסע שגיאה ראשונה": round(s.first_error_move.mean(), 1)})
    st.subheader("לפי צבע וקצב")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(f"הנחות וספים: שגיאה = ירידה של ≥{C.ERROR_DROP_CP} סנטיפון או מעבר ל‑{C.LOSING_CP}; "
               f"עומק {C.ENGINE_DEPTH} / {C.ENGINE_TIME} שניות; {C.ANALYZE_PLIES} חצאי‑מסעים ראשונים. פירוט ב‑README.")


def table_view(t):
    return pd.DataFrame({
        "צבע": t.color.map(COLORS), "רצף מסעים": t.line, "ECO": t.eco, "שם הפתיחה": t.opening,
        "משחקים": t.games, "ניצחון": t.win.map(pct), "תיקו": t.draw.map(pct), "הפסד": t.loss.map(pct),
        "ציון": t.score.map(lambda x: f"{x:.1%}"), "מסע שגיאה ראשונה": t.avg_first_error_move.round(1),
        "שגיאה מוקדמת": t.early_error_share.map(pct),
        "שגיאה נפוצה (אחרי הרצף)": t.top_error, "% משחקים עם שגיאה זו": t.top_error_share.map(pct), "רעילה": t.toxic.map(lambda b: "⚠️" if b else "")})


tbl = opening_table(fdf, base) if len(fdf) else pd.DataFrame()
with tab_tbl:
    st.write(f"קבוצות עם לפחות {C.MIN_GROUP_GAMES} משחקים. הקיבוץ לפי רצף המסעים עד נקודת הסטייה.")
    if tbl.empty:
        st.info("אין קבוצות שעומדות בסף עבור הסינון הנוכחי.")
    else:
        st.dataframe(table_view(tbl), hide_index=True, use_container_width=True)

with tab_tox:
    st.write(f"פתיחה רעילה: ציון נמוך מהממוצע הכללי ({base:.1%}) ולפחות {C.EARLY_ERROR_SHARE:.0%} "
             f"ממשחקיה עם שגיאה ראשונה עד מסע {C.EARLY_ERROR_MOVE}.")
    tox = tbl[tbl.toxic] if not tbl.empty else tbl
    if tox.empty:
        st.success("אין פתיחות רעילות עבור הסינון הנוכחי.")
    else:
        st.dataframe(table_view(tox.sort_values("score")), hide_index=True, use_container_width=True)


def board_svg(fen, played_uci, best_uci, color, size=440):
    arrows = []
    for uci, clr in ((played_uci, "#cc2222cc"), (best_uci, "#22aa22cc")):
        if uci:
            m = chess.Move.from_uci(uci)
            arrows.append(chess.svg.Arrow(m.from_square, m.to_square, color=clr))
    return chess.svg.board(chess.Board(fen), arrows=arrows, size=size,
                           orientation=chess.WHITE if color == "white" else chess.BLACK)


def game_links(ids, color, ply=None):
    return " · ".join(f"[{i}](https://lichess.org/{i}/{color}#{ply})" for i in ids[:12])


with tab_rec:
    col_pick = st.radio("צבע", list(COLORS), format_func=COLORS.get, horizontal=True, key="rc")
    hide_l = st.checkbox("הסתר טעויות שכבר למדתי (לא חזרתי עליהן ב‑3 הביקורים האחרונים בעמדה)", True)
    allp = get_problems(col_pick, "default", None, hide_l)
    if allp:
        st.subheader("כל השגיאות החוזרות")
        st.caption("**הגעתי** = כמה משחקים הגיעו לעמדה; **טעיתי** = בכמה מהם שיחקתי את המסע השגוי; **% טעיתי** = היחס. "
                   "**אחוז טעות אחרון** = מתוך 5 הביקורים האחרונים. **נלמד** = אחרי הטעות האחרונה הגעתי לעמדה "
                   "לפחות 3 פעמים ולא חזרתי עליה. **חומרה** = ממוצע הסנטיפונים שאבדו. לחצו על כותרת כדי למיין.")
        st.dataframe(pd.DataFrame({
            "רצף עד העמדה": [p["line"] for p in allp], "שיחקת": [p["played"] for p in allp],
            "מומלץ": [p["best_san"] for p in allp], "הגעתי": [p["reached"] for p in allp],
            "טעיתי": [p["mistakes"] for p in allp], "% טעיתי": [round(p["rate"], 2) for p in allp],
            "% טעות אחרון": [round(p["recent_rate"], 2) for p in allp],
            "סטטוס": [p["status"] for p in allp], "טעות אחרונה": [p["last_mistake"] for p in allp],
            "ביקורים מאז": [p["since_last"] for p in allp],
            "% מהמשחקים בצבע": [round(p["share"], 3) for p in allp],
            "חומרה ממוצעת": [round(p["avg_drop"]) for p in allp],
            "סך אובדן": [round(p["total_drop"]) for p in allp],
            "ציון במשחקים אלה": [round(p["score"], 2) for p in allp]}),
            hide_index=True, use_container_width=True,
            column_config={"% טעיתי": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                           "% טעות אחרון": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                           "% מהמשחקים בצבע": st.column_config.NumberColumn(format="%.1f%%", help="פעמים 100"),
                           "ציון במשחקים אלה": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    sort_by = st.radio("מיין את חמש העמדות המובילות לפי", ["default", "count", "avg_drop", "total_drop"],
                       format_func={"default": "חוזרות קודם, ואז סך אובדן", "count": "מספר חזרות",
                                    "avg_drop": "חומרה ממוצעת", "total_drop": "סך אובדן"}.get, horizontal=True)
    probs = get_problems(col_pick, sort_by, C.TOP_POSITIONS, hide_l)
    if not probs:
        st.info("אין שגיאות.")
    for n, p in enumerate(probs, 1):
        with st.expander(f"#{n} · {p['line']} · טעיתי {p['mistakes']}/{p['reached']} ({p['rate']:.0%}) · {p['status']} · חומרה: {p['avg_drop']:.0f} סנטיפון · סך אובדן: {p['total_drop']:.0f}",
                         expanded=n == 1):
            a, b = st.columns(2)
            with a:
                st.image(board_svg(p["fen"], p["played_uci"], p["best_uci"], col_pick))
            with b:
                st.markdown(f"**שיחקת:** {ltr(p['played'])} (חץ אדום)", unsafe_allow_html=True)
                st.markdown(f"**מומלץ ע״י Stockfish:** {ltr(p['best_san'])} (חץ ירוק)", unsafe_allow_html=True)
                st.markdown(f"ציון במשחקים אלה: {p['score']:.0%}")
                st.markdown("**משחקים:** " + game_links(p["games"], col_pick, p["ply"]))
                ex = p.get("explorer")
                if ex:
                    tot = ex["white"] + ex["draws"] + ex["black"]
                    st.markdown("**Lichess Opening Explorer (רמה דומה):**")
                    rows = []
                    for m in ex["moves"]:
                        t = m["white"] + m["draws"] + m["black"]
                        mine = m["white"] if col_pick == "white" else m["black"]
                        rows.append({"Move": m["san"], "Games": t, "Share": pct(t / tot) if tot else "",
                                     "Score": f"{(mine + m['draws'] / 2) / t:.0%}" if t else ""})
                    st.dataframe(pd.DataFrame(rows), hide_index=True)
                else:
                    st.caption("נתוני Opening Explorer אינם זמינים: ה‑API דורש טוקן. "
                               "הגדירו LICHESS_TOKEN והריצו מחדש (ראו README).")



# ---------------------------------------------------------------- board & practice
def position_at(moves_str, ply):
    """Board after `ply` half-moves, plus the last move (for highlighting)."""
    b, last = chess.Board(), None
    for san in moves_str.split()[:ply]:
        last = b.push_san(san)
    return b, last


def board_img(board, color, last=None, arrows=(), size=520):
    ar = []
    for uci, clr in arrows:
        if uci:
            m = chess.Move.from_uci(uci)
            ar.append(chess.svg.Arrow(m.from_square, m.to_square, color=clr))
    check = board.king(board.turn) if board.is_check() else None
    return chess.svg.board(board, arrows=ar, lastmove=last, check=check, size=size,
                           orientation=chess.WHITE if color == "white" else chess.BLACK)


RED, GREEN = "#cc2222cc", "#22aa22cc"


def moves_html(moves_str, upto, mark):
    out = []
    for i, san in enumerate(moves_str.split()[:upto]):
        num = f"{i // 2 + 1}." if i % 2 == 0 else ""
        cls = "background:#ffe08a;color:#000;border-radius:3px;padding:0 3px;" if i + 1 == mark else ""
        out.append(f'{num}<span style="{cls}">{san}</span>')
    return f'<div class="ltr" style="font-size:1.05rem;line-height:1.9">{" ".join(out)}</div>'


with tab_board:
    if fdf.empty or tbl.empty:
        st.info("אין מספיק נתונים בסינון הנוכחי.")
        st.stop()
    # ---- 1. what to work on: openings ranked by expected points lost vs. the overall average
    rank = tbl.copy()
    rank["cost"] = (rank.games * (base - rank.score)).clip(lower=0)
    rank = rank.sort_values("cost", ascending=False).reset_index(drop=True)
    st.subheader("1. על מה כדאי לעבוד?")
    st.caption("הפתיחות מדורגות לפי **נקודות שאבדו ביחס לממוצע** = משחקים × (ציון ממוצע כללי − ציון הפתיחה). "
               "בחרו שורה כדי לראות את השגיאות בה. אם לא נבחרה שורה – מוצגת הפתיחה בראש הרשימה.")
    view = pd.DataFrame({
        "דירוג": range(1, len(rank) + 1), "צבע": rank.color.map(COLORS), "רצף מסעים": rank.line,
        "שם הפתיחה": rank.opening, "משחקים": rank.games, "ציון": rank.score.round(2),
        "נקודות שאבדו": rank.cost.round(1), "שגיאה מוקדמת": rank.early_error_share.map(pct),
        "שגיאה נפוצה": rank.top_error, "% משחקים עם שגיאה זו": rank.top_error_share.map(pct),
        "רעילה": rank.toxic.map(lambda b: "⚠️" if b else "")})
    ev = st.dataframe(view, hide_index=True, use_container_width=True, on_select="rerun",
                      selection_mode="single-row", height=260,
                      column_config={"ציון": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    sel = ev.selection.rows[0] if ev.selection.rows else 0
    op = rank.iloc[sel]
    scope = fdf[(fdf.color == op.color) & (fdf.group == op.group)]
    st.markdown(f"**נבחרה:** {COLORS[op.color]} · {ltr(op.line)} · {ltr(op.opening)} · "
                f"{op.games} משחקים · ציון {op.score:.0%}", unsafe_allow_html=True)

    mode = st.radio("מצב", ["עיון בלוח", "בחן את עצמך"], horizontal=True)
    color = op.color
    occ_f = get_occ()
    occ_f = occ_f[occ_f.id.isin(fdf.id)]
    oprobs_all = problem_positions(scope, color, top=None, with_explorer=False, occ=occ_f,
                                   base=fdf[fdf.color == color].score.mean())
    info = {(p["key"], p["played"]): p for p in oprobs_all}
    hide_learned = st.checkbox("הסתר טעויות שכבר למדתי", True, key="hl_board")
    oprobs = [p for p in oprobs_all if not (hide_learned and p["status"] == LEARNED)]

    if mode == "עיון בלוח":
        errs = scope[scope.first_error_ply.notna()].copy()
        if errs.empty:
            st.success("אין שגיאות ראשונות בפתיחה הזו.")
        else:
            errs["key"] = errs.fen_before.map(lambda f: " ".join(f.split()[:4]))
            errs["info"] = [info.get((k, m)) for k, m in zip(errs.key, errs.played_san)]
            if hide_learned:
                errs = errs[[not (i and i["status"] == LEARNED) for i in errs["info"]]]
            errs = errs.sort_values("drop", ascending=False).reset_index(drop=True)
            st.subheader("2. השגיאות בפתיחה (מהחמורה לקלה)")
            if errs.empty:
                st.success("כל הטעויות בפתיחה הזו כבר נלמדו 🎉")
                st.stop()
            ev2 = st.dataframe(pd.DataFrame({
                "מסע": errs.first_error_move.astype(int), "שיחקת": errs.played_san,
                "מומלץ": [san_of(f, b) for f, b in zip(errs.fen_before, errs.best)],
                "חומרה (סנטיפון)": errs["drop"].round().astype(int),
                "% מהמשחקים בפתיחה": [f"{i['share']:.0%}" if i else "" for i in errs["info"]],
                "טעיתי / הגעתי": [f"{i['mistakes']}/{i['reached']}" if i else "" for i in errs["info"]],
                "סטטוס": [i["status"] if i else "" for i in errs["info"]],
                "הערכה לפני ← אחרי": [f"{a:+.0f} ← {b:+.0f}" for a, b in zip(errs.eval_before, errs.eval_after)],
                "תוצאה": errs.result.map(RESULTS), "משחק": errs.id}),
                hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", height=240)
            r = errs.iloc[ev2.selection.rows[0] if ev2.selection.rows else 0]
            err_ply = int(r.first_error_ply)
            ply = st.slider("מסע בלוח (חצאי‑מסעים)", 0, err_ply, err_ply - 1, key=f"ply_{r.id}",
                            help="גררו כדי לעבור על המהלכים עד השגיאה; בעמדת ההחלטה מוצגים החצים.")
            board, last = position_at(r.moves, ply)
            at_decision = ply == err_ply - 1
            a, b = st.columns([3, 2])
            with a:
                st.image(board_img(board, color, last,
                                   [(r.played, RED), (r.best, GREEN)] if at_decision else
                                   [(r.played, RED)] if ply == err_ply else []))
            with b:
                st.markdown(moves_html(r.moves, min(err_ply + 1, len(r.moves.split())), err_ply),
                            unsafe_allow_html=True)
                if at_decision:
                    st.error(f"כאן הטעות: שיחקת {r.played_san}")
                    st.success(f"מומלץ: {san_of(r.fen_before, r.best)}")
                    st.caption(f"הערכה לפני {r.eval_before:+.0f} ← אחרי {r.eval_after:+.0f} סנטיפון (מנקודת מבטך)")
                else:
                    st.caption("עברו לעמדת ההחלטה (המסע לפני השגיאה) כדי לראות את החצים.")
                st.markdown(f"[פתח את המשחק ב‑Lichess](https://lichess.org/{r.id}/{color}#{err_ply})")
    else:
        st.subheader("2. בחן את עצמך")
        if not oprobs:
            st.success("אין עמדות לתרגול בפתיחה הזו.")
        else:
            sig = f"{color}|{op.group}|{len(oprobs)}"
            if st.session_state.get("pr_sig") != sig:
                st.session_state.update(pr_sig=sig, pr_i=0, pr_ok=0, pr_n=0, pr_checked=None)
            i = st.session_state.pr_i
            if i >= len(oprobs):
                st.success(f"סיימת! {st.session_state.pr_ok} נכון מתוך {st.session_state.pr_n}.")
                if st.button("התחל מחדש"):
                    st.session_state.pr_sig = None
                    st.rerun()
            else:
                p = oprobs[i]
                board = chess.Board(p["fen"])
                rng = random.Random(p["key"] + p["played"])
                others = [m for m in (board.san(m) for m in board.legal_moves) if m not in (p["best_san"], p["played"])]
                opts = [p["best_san"], p["played"]] + rng.sample(others, min(2, len(others)))
                rng.shuffle(opts)
                checked = st.session_state.pr_checked
                a, b = st.columns([3, 2])
                with a:
                    st.image(board_img(board, color, None,
                                       [(p["played_uci"], RED), (p["best_uci"], GREEN)] if checked else []))
                with b:
                    st.markdown(f"**עמדה {i + 1} מתוך {len(oprobs)}** · ניקוד: {st.session_state.pr_ok}/{st.session_state.pr_n}")
                    st.markdown(f"תור ה{COLORS[color]} · הרצף עד כאן: {ltr(p['line'])}", unsafe_allow_html=True)
                    st.caption(f"טעיתי {p['mistakes']} מתוך {p['reached']} ביקורים בעמדה ({p['rate']:.0%}), טעות אחרונה {p['last_mistake']} · "
                               f"{p['status']} · חומרה ממוצעת {p['avg_drop']:.0f} סנטיפון.")
                    choice = st.radio("מה המסע הטוב ביותר?", opts, key=f"pr_choice_{sig}_{i}", disabled=bool(checked))
                    if not checked:
                        if st.button("בדוק", type="primary"):
                            ok = choice == p["best_san"]
                            st.session_state.pr_checked = {"choice": choice, "ok": ok}
                            st.session_state.pr_ok += int(ok)
                            st.session_state.pr_n += 1
                            st.rerun()
                    else:
                        if checked["ok"]:
                            st.success(f"נכון! {p['best_san']} הוא המסע של Stockfish.")
                        elif checked["choice"] == p["played"]:
                            st.error(f"זו בדיוק הטעות ששיחקת במשחקים. המסע המומלץ: {p['best_san']}")
                        else:
                            st.error(f"לא מדויק. המסע המומלץ: {p['best_san']} (ושיחקת בפועל {p['played']}).")
                        st.caption("אם בחרת מסע אחר שנראה לך סביר – ייתכן שגם הוא טוב; הבדיקה היא מול המסע הראשון של Stockfish.")
                        st.markdown("משחקים: " + game_links(p["games"], color, p["ply"]))
                        if st.button("הבא ←", type="primary"):
                            st.session_state.pr_i += 1
                            st.session_state.pr_checked = None
                            st.rerun()
