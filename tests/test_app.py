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
    first_card = next(m.value for m in at.markdown if 'class="plan-line"' in m.value)
    played = re.search(r'<b class="ltr">\d+\.(?:\.\.)?([^<]+)</b>', first_card).group(1)
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
    at = at.button(key="mk_next").click().run()
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
    open_btns = [b for b in at.button if b.label == "פתח ←"]
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


def test_drill_shows_the_trainer_card(monkeypatch):
    """Regression: the trainer card (board column and text column) must render on the mistake screen."""
    import ui.trainer
    monkeypatch.setattr(ui.trainer, "tr_node", lambda fen, color, rating: dict(
        mpv=[("d2d3", 30), ("c2c3", 20)], wins=[55.0, 50.0], gap=5.0, critical=False, level=None, masters=None,
        level_n=0, masters_n=0, level_err=None, known=False))
    at = run("yairklo", "mistakes", mk_drill=True)
    assert not at.exception, at.exception
    assert any("מסע 1: תור" in m.value for m in at.markdown)
    assert "→ חזרה לטעות" in labels(at)


def test_plan_and_mistake_list_order_match():
    at = run("plan3")
    expected = []
    for i in range(3):
        at = run("plan3")
        at = next(b for b in at.button if b.key == f"fix_{i}").click().run()
        keys = at.session_state["mk_sel"]
        crumb = next(m.value for m in at.markdown if "מתוך" in m.value and "mk-crumb" in m.value)
        assert f"**{i + 1} מתוך" in crumb, (i, crumb)
        expected.append(keys)
    assert len(set(expected)) == 3
    # first entry into the tab (no selection) starts at the plan's first mistake
    at = run("plan3", "mistakes")
    assert at.session_state["mk_sel"] == expected[0]


def test_settings_change_clears_the_trainer():
    at = run("plan3")
    at = next(b for b in at.button if b.key == "fix_0").click().run()
    assert at.session_state["mk_drill"] is True
    at.radio(key="thr_choice").set_value(8)
    at = at.run()
    assert at.session_state["mk_drill"] is False


def test_why_short_keeps_the_move_and_stays_short():
    from chessapp.lines import explain
    import chess
    # mate, material, missed chance and drops: any position works; the engine is not needed for the structure
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    x = explain(dict(fen=fen, played_uci="g8f6", best_uci="f8c5", color="black", ply=6, win_before=60.0, win_after=40.0))
    assert x["why_short"] and not x["why_short"].endswith("…")
    assert len(x["why_short"].split()) <= 16


def test_other_player_copy_is_third_person():
    for page in ("home", "repertoire"):
        at = run("plan3", page)
        words = " ".join(m.value for m in at.markdown if "gloss" not in m.value and "pill" not in m.value[:60])
        for w in ("אצלך", "אתה", "לך ", "שלך"):
            assert w not in re.sub(r"<[^>]+>", " ", words), (page, w)


def test_repertoire_lists_only_repeated_mistakes():
    at = run("plan3", "repertoire")
    assert not at.exception, at.exception
    assert len([b for b in at.button if b.label == "פתח ←"]) <= 2
    assert not any("פעם אחת" in c.value and "·" in c.value for c in at.caption)


def test_bidi_wraps_moves_and_numbers():
    from ui.common import bidi
    out = bidi("אחרי 6...Kxf7 יורדים מ־63% ל־56%")
    assert '<bdi dir="ltr">6...Kxf7</bdi>' in out and '<bdi dir="ltr">63</bdi>' in out


def test_why_short_names_the_punishing_move_in_percent_sentences():
    from chessapp.lines import explain
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    x = explain(dict(fen=fen, played_uci="g8f6", best_uci="f8c5", color="black", ply=6, win_before=60.0, win_after=40.0))
    if "סיכויי הניצחון" in x["why_short"]:
        assert x["why_short"].startswith("אחרי ")


def test_no_prefix_letter_glued_to_a_latin_name():
    at = run("plan0")      # not analysed: the subtitle names the player
    text_ = " ".join(m.value for m in at.markdown)
    assert "לplan0" not in text_


def test_repertoire_row_button_selects_the_node():
    at = run("plan3", "repertoire")
    rows = [b for b in at.button if b.key and b.key.startswith("op_white_")]
    assert len(rows) >= 2
    target = rows[1]
    at = target.click().run()
    assert at.session_state["op_key"] == target.key[len("op_white_"):]


def test_sensitivity_radio_shows_the_real_value_after_navigation():
    at = run("plan3", "home", thr=8)
    at = next(b for b in at.button if b.key == "fix_0").click().run()
    assert at.radio(key="thr_choice").value == at.session_state["thr"] == 8
