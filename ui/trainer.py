"""The line trainer: fix the mistake, then keep playing the line. Drawn inline on the Mistakes screen."""
import chess
import streamlit as st

from chessapp import config as C

from .board import chess_board, fresh_move
from .common import COLORS, GREEN, RED, chip, en, esc, line_html, md, move_label
from .ctx import ctx
from .data import level_view, tr_key

TR_STOP = {
    "quiet": "מכאן העמדה סלחנית: כמה מסעים טובים כמעט באותה מידה, והיא כבר לא נפוצה ברמה שלך או אצל מאסטרים. "
             "אין צורך לשנן הלאה.",
    "max": f"הגענו לתקרה של {C.TRAIN_MAX_MOVES} מסעים.",
    "over": "המשחק הסתיים.",
}


@st.cache_data(show_spinner="המנוע בודק את העמדה...")
def tr_node(fen, color, rating):
    from chessapp.trainer import node
    return node(chess.Board(fen), color, rating)


@st.cache_data(show_spinner="מחפש תגובות של היריב...")
def tr_opp(fen, rating, from_games):
    from chessapp.trainer import opponent_options
    return opponent_options(chess.Board(fen), rating, [dict(san=s, n=n) for s, n in from_games])


def tr_reset(key, mine_first, p):
    mine = chess.WHITE if p["color"] == "white" else chess.BLACK
    first = "me" if chess.Board(p["fen"]).turn == mine else "opp"
    st.session_state.update(tr_sig=(key, mine_first), tr_moves=[], tr_turn=first, tr_done=0, tr_quiet=0, tr_log=[],
                            tr_answer=None, tr_decided=-1, tr_reason=None, tr_stop=None, tr_snaps=[])
    if mine_first:  # train the line that follows the player's own move (it works at the player's level)
        st.session_state.update(tr_moves=[p["played_uci"]], tr_turn="opp", tr_done=1,
                                tr_log=[dict(san=p["played"], ok=True, drop=0, reason="mine", best=p["played"], chosen=p["played"])])


def tr_answer(board, info, uci, color):
    from chessapp.trainer import evaluate
    st.session_state.tr_answer = evaluate(board, info, uci, color)


def tr_continue(board):
    a = st.session_state.tr_answer
    move = a["uci"] if a["ok"] else a["best"]
    san = lambda u: board.san(chess.Move.from_uci(u))
    st.session_state.tr_log.append(dict(san=san(move), chosen=san(a["uci"]), best=san(a["best"]), ok=a["ok"],
                                        drop=a["drop"], is_best=a["is_best"], reason=st.session_state.tr_reason))
    st.session_state.tr_moves.append(move)
    st.session_state.update(tr_done=st.session_state.tr_done + 1, tr_turn="opp", tr_answer=None)


def tr_opp_pick(uci):
    snap = {k: (list(v) if isinstance(v, list) else v) for k, v in st.session_state.items()
            if k in ("tr_moves", "tr_done", "tr_quiet", "tr_log", "tr_decided")}
    st.session_state.tr_snaps.append(snap)
    st.session_state.tr_moves.append(uci)
    st.session_state.tr_turn = "me"


def tr_back():
    snap = st.session_state.tr_snaps.pop()
    st.session_state.update(**snap, tr_turn="opp", tr_answer=None, tr_stop=None)


def drill(p):
    """The line trainer for mistake `p`, drawn inside the Mistakes screen."""
    from chessapp.trainer import decide, my_options
    key = tr_key(p)
    lv = level_view(p)
    mine_first = False
    if lv and lv.get("works") and p.get("played_uci"):
        mine_first = st.radio("מה לתרגל?", [False, True], horizontal=True, key=f"tr_variant_{key}",
                              format_func={False: f"הקו של המנוע ({p['best_san']})",
                                           True: f"המסע שלי ({p['played']}) והמשכו – הוא עובד ברמה שלי"}.get)
    if st.session_state.get("tr_sig") != (key, mine_first):
        tr_reset(key, mine_first, p)

    color = p["color"]
    rating = int(ctx.fdf[ctx.fdf.color == color].rating.median())
    board = chess.Board(p["fen"])
    sans = []
    for u in st.session_state.tr_moves:
        m = chess.Move.from_uci(u)
        sans.append(board.san(m))
        board.push(m)
    last = board.move_stack[-1] if board.move_stack else None
    turn = st.session_state.tr_turn

    info = None
    if turn == "me":
        info = tr_node(board.fen(), color, rating)
        if st.session_state.tr_decided != len(st.session_state.tr_moves):
            go_on, quiet, reason = decide(st.session_state.tr_done, st.session_state.tr_quiet, info, board)
            st.session_state.update(tr_decided=len(st.session_state.tr_moves), tr_quiet=quiet, tr_reason=reason)
            if not go_on:
                st.session_state.update(tr_turn="done", tr_stop=reason)
                turn = "done"

    with st.container(border=True, key="card_trainer"):
        ans = st.session_state.tr_answer
        done = st.session_state.tr_done
        title = {"me": f"מסע {done + 1}: תור ה{COLORS[color]}. מה הכי טוב?",
                 "opp": "תור היריב: איך הוא עונה?"}.get(turn, "סוף הקו")
        md(f'<div class="card-h">{chip(color)}<span class="t">{en(p["opening"])}</span>'
           f'<span class="mk-sub">· {esc(title)}</span></div>')
        arrows, options, interactive, allow = [], [], False, None
        if turn == "me" and ans:
            arrows = [(ans["uci"], GREEN if ans["ok"] else RED)] + ([] if ans["is_best"] else [(ans["best"], GREEN)])
        elif turn == "me":
            mistake = p["played_uci"] if not st.session_state.tr_moves else None
            options = [dict(uci=u, label=board.san(chess.Move.from_uci(u))) for u in my_options(board, info, mistake)]
            interactive = True
        elif turn == "opp":
            from_games = tuple((r["san"], r["n"]) for r in p["replies"]) if mine_first and len(sans) == 1 else ()
            opp = tr_opp(board.fen(), rating, from_games)
            if not opp:
                st.session_state.update(tr_turn="done", tr_stop="over")
                st.rerun()
            options = [dict(uci=o["uci"], label=o["san"], sub=" · ".join(o["tags"])) for o in opp]
            interactive, allow = True, {o["uci"] for o in opp}
        shown, shown_last = board, last
        if turn == "me" and ans and ans["ok"]:
            # an accepted move is shown on the board (the piece moves), not as an arrow
            shown = board.copy()
            shown_last = chess.Move.from_uci(ans["uci"])
            shown.push(shown_last)
            arrows = []
        sig = abs(hash(st.session_state.get("tr_sig")))
        val = chess_board(shown, color, key=f"trb_{sig}_{len(sans)}_{turn}_{int(bool(ans))}", arrows=arrows,
                          last=shown_last, options=options, interactive=interactive, allow=allow, size=400, side=True)
        mv = fresh_move(val, "tr_token", board) if interactive else None
        if mv and turn == "me":
            tr_answer(board, info, mv, color)
            st.rerun()
        elif mv and turn == "opp":
            tr_opp_pick(mv)
            st.rerun()
        if sans:
            md(line_html(sans, p["ply"], len(sans)))

        if turn == "me" and ans:
            chosen = board.san(chess.Move.from_uci(ans["uci"]))
            best = board.san(chess.Move.from_uci(ans["best"]))
            if ans["is_best"]:
                st.success(f"נכון! {chosen} הוא המסע הטוב ביותר.", icon=":material/check_circle:")
            elif ans["ok"]:
                st.success(f"גם טוב: {chosen} " + (f"שווה בערכו ל־{best}" if ans["drop"] < 1 else
                                                   f"רק {ans['drop']:.0f}% פחות מ־{best}") + ". ממשיכים עם המסע שלך.",
                           icon=":material/check_circle:")
            else:
                st.error(f"{chosen} מוריד את סיכויי הניצחון ב־{ans['drop']:.0f}%. הטוב ביותר: {best}. "
                         f"ממשיכים עם {best}.", icon=":material/cancel:")
            st.button("המשך", type="primary", on_click=tr_continue, args=(board,), icon=":material/arrow_back:")
        elif turn == "done":
            log = st.session_state.tr_log
            own = [l for l in log if l.get("reason") != "mine"]
            ok = sum(l["ok"] for l in own)
            rows = "".join(
                f'<tr><td>{"✓" if l["ok"] else "✗"}</td><td><span class="ltr">{esc(l["chosen"])}</span></td>'
                f'<td>{"" if l["ok"] else en(l["best"])}</td></tr>' for l in own)
            md(f'<div class="card-h"><span class="t" style="font-size:1.15rem">סוף הקו: {ok} מתוך {len(own)} נכונים</span></div>'
               f'<div class="level">{TR_STOP.get(st.session_state.tr_stop, "")}</div>'
               f'<table class="replies"><tr><th></th><th>בחרת</th><th>הטוב ביותר</th></tr>{rows}</table>')
            c1, c2 = st.columns(2)
            if st.session_state.tr_snaps:
                c1.button("תגובה אחרת של היריב", on_click=tr_back, width="stretch", icon=":material/alt_route:")
            c2.button("מההתחלה", on_click=tr_reset, args=(key, mine_first, p), width="stretch", icon=":material/replay:")
    if not C.lichess_token() and not st.session_state.get("tr_token_note_shown"):
        st.session_state.tr_token_note_shown = True   # once per session, not on every move
        st.caption("בלי טוקן של Lichess האימון עובד רק לפי המנוע (בלי \"נפוץ ברמה שלך\" ובלי מסד המאסטרים).")
