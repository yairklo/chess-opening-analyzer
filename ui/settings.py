"""Settings (the popover behind the header's gear): player, colour, sensitivity, engine and token status,
glossary and statistics. The selected values live in `st.session_state` under fixed widget keys, so they survive
navigation between screens."""
import altair as alt
import pandas as pd
import streamlit as st

from chessapp import config as C
from chessapp.analyze import build_results
from chessapp.fetch_games import FetchError, fetch

from .common import COLORS, SPEEDS, STATUS_ME, STATUS_OTHER, en, ltr_label, md
from .ctx import ctx
from .data import data_stamp, get_data, job_state, start_analysis

def _reset_drill():
    st.session_state.update(mk_drill=False, quiz=False, rp_drill=None)


def _set_threshold():
    """The radio's own key holds only what the widget shows; the real value lives in session_state['thr']."""
    st.session_state.thr = st.session_state.thr_choice
    _reset_drill()


SENSITIVITY = {20: "רק טעויות גסות", 12: "רגיל", 8: "גם אי־דיוקים"}
SENSITIVITY_HELP = {20: "מסעים שמורידים הרבה מהסיכויים", 12: "מומלץ", 8: "יותר טעויות, חלקן קטנות"}


@st.fragment(run_every=3)
def analysis_progress(user):
    state, k, n = job_state(user)
    if state == "running":
        st.progress(k / n if n else 0.0, text=f"Stockfish מנתח: {k} מתוך {n or '?'} משחקים")
        st.caption("אפשר להמשיך לעבוד בינתיים – הטעויות יופיעו כשהניתוח יסתיים.")
    else:
        st.rerun(scope="app")


def engine_panel(user, has_errors, stamp):
    """Engine analysis status for the selected player."""
    state, _, _ = job_state(user)
    if state == "running":
        analysis_progress(user)
    elif has_errors:
        st.caption(f"✓ נותח ב־Stockfish (עומק {C.ENGINE_DEPTH}).")
    else:
        if state == "failed":
            st.error("הניתוח נכשל. אפשר לנסות שוב.")
        n = stamp[0] if stamp else 0
        st.caption(f"הטעויות בפתיחה עוד לא נותחו. ניתוח {n:,} משחקים לוקח בערך {max(1, round(n * 0.65 / 60))} דקות.")
        st.button(ltr_label("נתח טעויות ב־", "Stockfish"), on_click=start_analysis, args=(user,), icon=":material/memory:",
                  width="stretch", key="run_engine")


def add_player(name, n, run_engine=True):
    name = name.strip()
    try:
        with st.status(f"מוריד את {n} המשחקים האחרונים של {name}...", expanded=True) as box:
            line = st.empty()
            got = fetch(name, refresh=True, max_games=n, on_progress=lambda k: line.write(f"{k} משחקים..."))
            line.write(f"{got} משחקים הורדו. בונה את עץ הפתיחות...")
            build_results(name)
            if run_engine:
                start_analysis(name.lower())
                line.write(f"{got} משחקים הורדו. ניתוח הטעויות ב־Stockfish התחיל ברקע.")
            box.update(label=f"{name} נטען", state="complete")
    except FetchError as e:
        st.error({"not found": f"לא נמצא ב־Lichess שחקן בשם '{name}'.", "valid": "שם המשתמש לא תקין."}.get(
            next((k for k in ("not found", "valid") if k in str(e)), ""), f"לא נמצאו משחקים עבור '{name}'."))
        return
    except Exception as e:  # network problems, rate limits...
        st.error(f"ההורדה נכשלה: {e}")
        return
    st.session_state.pending_user = name.lower()
    st.rerun()


def settings_controls(pop, players):
    """Draw the controls inside `pop`; returns the selection (player, colours, threshold, speeds, data).
    Order: what is changed most often first (player, colour, sensitivity, token), then collapsed sections."""
    with pop:
        user = st.selectbox("שחקן", players, key="user",
                            format_func=lambda u: f"{u} (אני)" if u == C.USER.lower() else u, on_change=_reset_drill)
        me = user == C.USER.lower()
        pick = st.segmented_control("אני משחק עם" if me else "צבע", ["all", "white", "black"], default="all",
                                    key="f_color", format_func={"all": "שני הצבעים", **COLORS}.get, width="stretch",
                                    on_change=_reset_drill)
        colors = [pick] if pick in COLORS else list(COLORS)
        if st.session_state.get("thr") not in SENSITIVITY:  # a value left over from the old slider
            st.session_state.thr = C.ERROR_WIN_DROP
        # `index` is part of the widget's identity: when the value is changed elsewhere (lower sensitivity, tests)
        # the radio is rebuilt with the right option selected instead of keeping a stale frontend state
        st.radio("רגישות: כמה גדולה טעות צריכה להיות", list(SENSITIVITY), key="thr_choice",
                       index=list(SENSITIVITY).index(st.session_state.thr),
                       format_func=SENSITIVITY.get, captions=[SENSITIVITY_HELP[v] for v in SENSITIVITY],
                       on_change=_set_threshold,
                       help="\"רק טעויות גסות\" מציג מסעים שמורידים את סיכויי הניצחון בלפחות 20 נקודות אחוז, "
                            "\"רגיל\" 12, \"גם אי־דיוקים\" 8. השינוי מיידי, בלי להריץ שוב את המנוע.")
        if C.lichess_token():
            st.markdown('<span class="pill green">מחובר ל־Lichess</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="pill gray">לא מחובר</span> טוקן Lichess מוסיף את "מה משחקים ברמה שלך". '
                        'איך מחברים? ראו README.', unsafe_allow_html=True)
        stamp = data_stamp(user)
        analyzed = bool(stamp and stamp[2])
        engine_panel(user, analyzed, stamp)
        thr = st.session_state.thr
        df, all_errors = get_data(user, stamp, thr)
        avail = [s for s in SPEEDS if s in set(df.speed)] + sorted(set(df.speed) - set(SPEEDS))
        if len(avail) > 1:
            speeds = st.multiselect("קצב משחק", avail, avail, format_func=lambda s: SPEEDS.get(s, s), key=f"speeds_{user}")
        else:
            speeds = avail
        with st.expander("ניהול משחקים", icon=":material/download:"):
            st.markdown(ltr_label("הורדה מחדש של המשחקים האחרונים של ", user, " מ־Lichess"))
            st.caption("משחקים חדשים נכנסים לעץ ולסטטיסטיקות, ועמדות שכבר נותחו לא מנותחות שוב.")
            n_refresh = st.segmented_control("כמה משחקים אחרונים", [200, 500, 1000], default=500, key="refresh_n")
            if st.button("הורד ועדכן", key="refresh_games", icon=":material/refresh:", width="stretch"):
                add_player(user, n_refresh or 500, True)
            st.divider()
            st.markdown(ltr_label("הוספת שחקן מ־", "Lichess"))
            with st.form("add_player", border=False, clear_on_submit=True):
                name = st.text_input(ltr_label("שם משתמש ב־", "Lichess"), placeholder="DrNykterstein", key="add_name")
                n_games = st.segmented_control("כמה משחקים אחרונים", [200, 500, 1000], default=500)
                run_engine = st.checkbox(ltr_label("לנתח מיד גם את הטעויות ב־", "Stockfish", " (ברקע)"), True)
                st.caption("ההורדה לוקחת בערך דקה לכל 500 משחקים, ועץ הפתיחות והחולשות מוכנים מיד אחריה. "
                           "ניתוח הטעויות לוקח עוד כ‑5 דקות לכל 500 משחקים, ואפשר להמשיך לעבוד בזמן שהוא רץ.")
                go_add = st.form_submit_button("הורד ונתח", type="primary", width="stretch")
            if go_add and name.strip():
                add_player(name, n_games or 500, run_engine)
        status = STATUS_ME if me else STATUS_OTHER
        who = "שלך" if me else "של השחקן"
        with st.expander("מילון מונחים", icon=":material/help:"):
            md(f"""<dl class="gloss">
<dt>אחוז נקודות</dt><dd>ניצחון = נקודה, תיקו = חצי. 50% = מאזן שוויוני.</dd>
<dt>טעות בפתיחה</dt><dd>מסע ב‑{C.ANALYZE_PLIES // 2} המסעים הראשונים שמוריד את סיכויי הניצחון ב‑{thr}% או יותר (לפי הרגישות שנבחרה). מסע שהוא המסע של המנוע אף פעם לא נחשב טעות.
מסעים שהם חלק מקו פתיחה שמשחקים קבוע (למשל גמביט) לא נחשבים טעות.</dd>
<dt>נקודות שאבדו</dt><dd>כמה נקודות הפתיחה עלתה לעומת הממוצע {who} באותו צבע: משחקים × (הממוצע − אחוז הנקודות בפתיחה).</dd>
<dt>פתיחה בעייתית</dt><dd>אחוז נקודות נמוך ב‑{C.TOXIC_MARGIN:.0%} לפחות מהממוצע {who} באותו צבע, טעות עד מסע {C.EARLY_ERROR_MOVE} ב‑{C.EARLY_ERROR_SHARE:.0%} או יותר מהמשחקים,
וגם אותה טעות בדיוק ב‑{C.MIN_PROBLEM_GAMES} משחקים לפחות.</dd>
<dt>טעות חוזרת</dt><dd>אותו מסע שגוי באותה עמדה ב‑{C.MIN_PROBLEM_GAMES} משחקים או יותר (ב‑2 משחקים כשאין כאלה).</dd>
<dt>טעות שנלמדה</dt><dd>{status["learned"][2]}</dd>
<dt>מוקדם לדעת</dt><dd>ההבדל מהממוצע קטן או מבוסס על מעט משחקים, ולכן אפשר שהוא מקרי.</dd>
</dl>""")
            st.caption(f"ניתוח המנוע: Stockfish בעומק {C.ENGINE_DEPTH} קבוע לכל עמדה. "
                       f"פתיחה מוצגת רק אם שוחקה {C.MIN_GROUP_GAMES}+ פעמים.")
    return dict(user=user, me=me, stamp=stamp, analyzed=analyzed, colors=colors, thr=thr, speeds=speeds,
                df=df, all_errors=all_errors)


def chart_rating(by_time):
    d = by_time.assign(date=pd.to_datetime(by_time.created, unit="ms"))
    d = d.groupby(d.date.dt.normalize()).rating.last().reset_index()
    y = alt.Y("rating:Q", title=None, scale=alt.Scale(zero=False, padding=20))
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m", tickCount=6))
    base_c = alt.Chart(d)
    ch = (base_c.mark_line(color="#2563eb", strokeWidth=2.5)
          + base_c.mark_point(color="#2563eb", filled=True, size=26, opacity=0)
          .encode(tooltip=[alt.Tooltip("date:T", title="תאריך", format="%d.%m.%Y"), alt.Tooltip("rating:Q", title="דירוג")]))
    return ch.encode(x=x, y=y).properties(height=200)


def settings_stats(pop, by_time, main_speed):
    """The rating chart, kept out of the home page."""
    with pop:
        with st.expander("סטטיסטיקה", icon=":material/show_chart:"):
            st.caption(f"דירוג {SPEEDS.get(main_speed, main_speed)} לאורך זמן")
            st.altair_chart(chart_rating(by_time), width="stretch")
