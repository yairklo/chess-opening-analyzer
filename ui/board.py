"""Interactive board: pieces can be dragged (or clicked) to make a move, and hovering over an answer option
highlights that move on the board. A small hand-written Streamlit component (no build step, no external library);
the frontend is `board_frontend/index.html`.

`chess_board(...)` returns None until the user acts, then {"uci", "via": "board" | "option", "token"}. The value
stays in place on later reruns, so callers must act on each token only once (see `fresh_move`)."""
from functools import lru_cache
from pathlib import Path

import chess
import chess.svg
import streamlit as st
import streamlit.components.v1 as components

_component = components.declare_component("chess_board", path=str(Path(__file__).parent / "board_frontend"))

ARROW_RED, ARROW_GREEN = "#dc2626", "#16a34a"


@lru_cache(maxsize=1)
def _pieces():
    return {p.symbol(): chess.svg.piece(p, size=45) for c in chess.COLORS for p in
            (chess.Piece(t, c) for t in chess.PIECE_TYPES)}


def legal_map(board, allow=None):
    """{from-square: [to-squares]} for the side to move; `allow` restricts it to a set of UCI moves."""
    out = {}
    for m in board.legal_moves:
        if allow is not None and m.uci() not in allow:
            continue
        frm = chess.square_name(m.from_square)
        targets = out.setdefault(frm, [])
        to = chess.square_name(m.to_square)
        if to not in targets:
            targets.append(to)
        if board.is_castling(m):  # the king may also be dropped on its own rook (how Lichess accepts castling)
            rook = chess.square(7 if board.is_kingside_castling(m) else 0, chess.square_rank(m.from_square))
            rook_name = chess.square_name(rook)
            if rook_name not in targets:
                targets.append(rook_name)
    return out


def _arrow(uci, color):
    return {"from": uci[:2], "to": uci[2:4], "color": color}


def chess_board(board, color, *, key, arrows=(), last=None, options=(), interactive=True, allow=None, size=460,
                side=False):
    """Draw `board` from `color`'s side. `arrows`: [(uci, "#rrggbb")]; `options`: [{"uci", "label", "sub"?}] shown
    as buttons under the board (or beside it with `side=True`); `allow`: restrict draggable moves to these UCIs
    (default: every legal move)."""
    return _component(
        fen=board.fen(), orientation=color, size=size, side=bool(side), interactive=bool(interactive),
        legal=legal_map(board, allow) if interactive else {}, pieces=_pieces(),
        arrows=[_arrow(u, c[:7]) for u, c in arrows if u],
        last=[chess.square_name(last.from_square), chess.square_name(last.to_square)] if last else None,
        options=[dict(o) for o in options], key=key, default=None)


def fresh_move(value, state_key, board):
    """The UCI of a move the user just made, or None. A returned value is kept by Streamlit on later reruns, so
    every token is accepted once (remembered in session_state[state_key]) and the move must be legal here."""
    if not value or value.get("token") == st.session_state.get(state_key):
        return None
    st.session_state[state_key] = value.get("token")
    try:
        move = board.parse_uci(value["uci"])   # king-takes-rook (e1h1) becomes the castling move e1g1
    except (KeyError, ValueError):
        return None
    return move.uci() if move in board.legal_moves else None
