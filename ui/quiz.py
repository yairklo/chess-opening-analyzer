"""תרגול מהיר: a two-minute quiz over the recurring mistakes (one move per position)."""
import random

import chess
import streamlit as st

from chessapp import config as C
from chessapp.stats import SORTS

from .board import chess_board, fresh_move
from .common import COLORS, GREEN, RED, arrow_legend, chip, in_times, empty, en, esc, game_links, md, moves_html, set_state
from .ctx import ctx
from .data import level_view, recurring

QUIZ_SIZE = 10


def answer(choice, best):
    st.session_state.pr_answer = choice
    st.session_state.pr_n += 1
    st.session_state.pr_ok += int(choice == best)


def next_q():
    st.session_state.pr_i += 1
    st.session_state.pr_answer = None



def close_quiz():
    st.session_state.quiz = False


def page_quiz():
    st.button("→ חזרה", key="quiz_close", on_click=close_quiz)
    md('<h1 class="plan-h1">תרגול מהיר</h1><p class="plan-sub">העמדות שבהן טעית. מצאו את המסע הטוב ביותר, כמו במשחק אמיתי.</p>')
    items = sorted(recurring([p for p in ctx.probs if p["status"] != "learned"]), key=SORTS["default"])[:QUIZ_SIZE * 2]
    if C.lichess_token():
        items = [p for p in items if not (level_view(p) or {}).get("works")]
    items = items[:QUIZ_SIZE]
    if not items:
        empty("אין כרגע טעויות חוזרות לתרגל. 🎉")
        return

    sig = f"{ctx.user}|{len(items)}|{ctx.thr}"
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
            options = [] if ans else [dict(uci=board.parse_san(m).uci(), label=m) for m in opts]
            val = chess_board(board, p["color"], key=f"quizb_{sig}_{i}_{int(bool(ans))}",
                              arrows=[(p["played_uci"], RED), (p["best_uci"], GREEN)] if ans else [],
                              options=options, interactive=not ans)
            mv = None if ans else fresh_move(val, "quiz_token", board)
            if mv:
                answer(board.san(chess.Move.from_uci(mv)), p["best_san"])
                st.rerun()
            if ans:
                md(arrow_legend())
        with b:
            md(f'<div class="card-h">{chip(p["color"])}<span class="t">{en(p["opening"])}</span></div>'
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
                md('<div class="note">גררו כלי על הלוח, או בחרו אפשרות מתחת ללוח (מעבר עם העכבר מסמן אותה על הלוח).</div>')
            if ans:
                if ans == p["best_san"]:
                    st.success(f"נכון! {p['best_san']} הוא המסע ש־Stockfish ממליץ עליו.", icon=":material/check_circle:")
                elif ans == p["played"]:
                    st.error(f"זה בדיוק המסע ששיחקת במשחקים ({in_times(p['mistakes'], p['reached'])}). "
                             f"עדיף {p['best_san']}.", icon=":material/cancel:")
                else:
                    st.warning(f"לא זה. המסע המומלץ הוא {p['best_san']}; במשחקים שיחקת {p['played']}.", icon=":material/info:")
                md('<div class="note">ייתכן שגם מסע אחר סביר – הבדיקה היא מול המסע הראשון של Stockfish.</div>'
                   + game_links(p["games"], p["color"], p["ply"], 6))
                st.button("לעמדה הבאה", type="primary", on_click=next_q, width="stretch", icon=":material/arrow_back:")
            else:
                md(f'<div class="note">כאן טעית {in_times(p["mistakes"], p["reached"])} שהגעת לעמדה.</div>')
