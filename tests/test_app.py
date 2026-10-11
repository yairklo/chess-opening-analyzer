"""Smoke tests for the dashboard (Streamlit AppTest) on the synthetic players from conftest.py.

Not covered here (checked by hand in screenshots): "at most 12 numbers" on the home page and "no scrolling at
1280x800" on the mistake screen."""
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ui.data

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = ["home", "mistakes", "repertoire"]
FIX = "לתקן עכשיו ←"
OPEN = "לפתיחה ←"


@pytest.fixture(autouse=True)
def no_engine(monkeypatch):
    """explain() would start Stockfish; the screens only need a sentence."""
    monkeypatch.setattr(ui.data, "explain", lambda p: dict(
        punish="", punish_first=None, punish_sans=[], better_sans=[], better="", lost=1, gain=0, url="https://lichess.org/",
        why="המסע נותן פרש, ולכן היריב מקבל יתרון ברור כבר בפתיחה ובלי פיצוי של ממש."))
    ui.data.get_explain.clear()


def run(user, page="home", **state):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["user"] = user
    at.session_state["page"] = page
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def labels(at):
    return [b.label for b in at.button]


def text(at):
    return " ".join(m.value for m in at.markdown)


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("user", ["plan3", "plan1", "plan0"])
def test_every_screen_loads_without_errors(user, page):
    at = run(user, page)
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


def test_home_has_three_plan_cards_when_three_recurring_mistakes_exist():
    at = run("plan3")
    assert labels(at).count(FIX) == 3
    assert OPEN not in labels(at)
    # the learned mistake (g4, "h3") is not in the plan
    assert "7.h3" not in text(at)


def test_home_fills_up_with_weak_openings():
    at = run("plan1")
    assert labels(at).count(FIX) == 1
    assert labels(at).count(OPEN) == 2


def test_home_empty_state_offers_lower_sensitivity():
    at = run("plan0")
    assert FIX not in labels(at)
    assert "להפחית את הרגישות ←" in labels(at)


def test_fix_now_opens_the_matching_mistake():
    at = run("plan3")
    first_card = next(m.value for m in at.markdown if 'class="plan-text"' in m.value)
    played = re.search(r'<span class="ltr">\d+\.(?:\.\.)?([^<]+)</span>', first_card).group(1)
    fix = next(b for b in at.button if b.label == FIX)
    at = fix.click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "mistakes"
    color, _, played_key = at.session_state["mk_sel"].split("|")
    assert played_key == played
    assert f"{played}?" in text(at)


def test_mistake_screen_walks_through_the_list():
    at = run("plan3", "mistakes")
    assert any(re.search(r"\*\*1 מתוך \d+\*\*", m.value) for m in at.markdown)
    first = at.session_state["mk_sel"]
    at = next(b for b in at.button if b.label == "הבאה ›").click().run()
    assert at.session_state["mk_sel"] != first
    assert any(re.search(r"\*\*2 מתוך \d+\*\*", m.value) for m in at.markdown)


def test_settings_survive_navigation():
    at = run("plan1", "home", thr=8)
    for page in ("mistakes", "repertoire", "home"):
        at.session_state["page"] = page
        at = at.run()
        assert not at.exception, at.exception
    assert at.session_state["user"] == "plan1"
    assert at.session_state["thr"] == 8


def test_repertoire_opens_a_mistake():
    at = run("plan3", "repertoire")
    open_btns = [b for b in at.button if b.label == "לטעות ←"]
    assert open_btns
    at = open_btns[0].click().run()
    assert at.session_state["page"] == "mistakes"
    assert not at.exception, at.exception


def test_quiz_loads_with_the_interactive_board():
    at = run("yairklo", "home", quiz=True)
    assert not at.exception, at.exception
    assert any("תרגול מהיר" in m.value for m in at.markdown)


def test_board_helpers():
    import chess
    from ui.board import fresh_move, legal_map
    b = chess.Board()
    legal = legal_map(b)
    assert sorted(legal["e2"]) == ["e3", "e4"] and "e1" not in legal
    assert legal_map(b, {"e2e4"}) == {"e2": ["e4"]}
    import streamlit as st
    st.session_state.clear()
    assert fresh_move({"uci": "e2e4", "token": "t1"}, "tok", b) == "e2e4"
    assert fresh_move({"uci": "e2e4", "token": "t1"}, "tok", b) is None      # the same token twice
    assert fresh_move({"uci": "e2e5", "token": "t2"}, "tok", b) is None      # not a legal move
