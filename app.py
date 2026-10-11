"""Streamlit dashboard: opening analysis for a Lichess player (Hebrew, RTL).

Three screens (התוכנית שלי / טעויות / הפתיחות שלי) and a settings popover; each screen lives in `ui/`."""
import streamlit as st

st.set_page_config(page_title="ניתוח פתיחות", page_icon="♞", layout="wide", initial_sidebar_state="collapsed")

from chessapp import config as C  # noqa: E402
from chessapp.analyze import users  # noqa: E402
from ui.common import SPEEDS, empty, esc, inject_css  # noqa: E402
from ui.ctx import ctx  # noqa: E402
from ui.data import get_problems, get_view  # noqa: E402
from ui.home import page_home  # noqa: E402
from ui.mistake import page_mistakes  # noqa: E402
from ui.quiz import page_quiz  # noqa: E402
from ui.repertoire import page_repertoire  # noqa: E402
from ui.settings import settings_controls, settings_stats  # noqa: E402

PAGES = {"home": "התוכנית", "mistakes": "טעויות", "repertoire": "הפתיחות"}
PAGES_MINE = {"home": "התוכנית שלי", "mistakes": "טעויות", "repertoire": "הפתיחות שלי"}
SCREENS = {"home": page_home, "mistakes": page_mistakes, "repertoire": page_repertoire}


def leave_quiz():
    st.session_state.update(quiz=False, mk_drill=False)


inject_css()
players = users()
if not players:
    st.error("לא נמצאו תוצאות ניתוח. הריצו קודם בטרמינל: python run_all.py")
    st.stop()
if "pending_user" in st.session_state:  # set by add_player before the selectbox exists
    st.session_state.user = st.session_state.pop("pending_user")
if st.session_state.get("user") not in players:
    st.session_state.user = players[0]

# ---------------------------------------------------------------- header + settings
if st.session_state.get("page") not in PAGES:
    st.session_state.page = "home"
with st.container(key="topbar"):
    c_brand, c_nav, c_who, c_gear = st.columns([1.5, 3.6, 2.6, 1.3], vertical_alignment="center")
c_brand.markdown('<span class="brand-top">♞ ניתוח פתיחות</span>', unsafe_allow_html=True)
labels = PAGES_MINE if st.session_state.get("user", players[0]) == C.USER.lower() else PAGES
page = c_nav.segmented_control("ניווט", list(PAGES), key="page", format_func=labels.get, label_visibility="collapsed",
                               on_change=leave_quiz)
pop = c_gear.popover("הגדרות", icon=":material/settings:", width="stretch")
head = c_who
sel = settings_controls(pop, players)
user, colors, speeds, thr, df = sel["user"], sel["colors"], sel["speeds"], sel["thr"], sel["df"]

if df[df.color.isin(colors) & df.speed.isin(speeds)].empty:
    head.markdown(f"**{esc(user)}**")
    empty("אין משחקים שמתאימים לסינון. שנו את הבחירה בהגדרות (⚙).")
    st.stop()

fdf, rel, tbl = get_view(user, sel["stamp"], thr, tuple(colors), tuple(speeds))
probs = get_problems(user, sel["stamp"], thr, tuple(colors), tuple(speeds))
ctx.set(user=user, me=sel["me"], analyzed=sel["analyzed"], colors=colors, speeds=speeds, thr=thr,
        df=df, all_errors=sel["all_errors"], fdf=fdf, rel=rel, tbl=tbl, probs=probs)

chosen = df[df.speed.isin(speeds)]
main_speed = chosen.speed.mode().iat[0]  # ratings are per speed: use the most played one
by_time = chosen[chosen.speed == main_speed].sort_values("created")
head.markdown(f'<span class="who"><span class="av">{esc(user[:1].upper())}</span><span dir="ltr">{esc(user)}</span>'
              f'<span class="sep">·</span>{int(by_time.rating.iat[-1])} {SPEEDS.get(main_speed, main_speed)}</span>',
              unsafe_allow_html=True)
settings_stats(pop, by_time, main_speed)

# ---------------------------------------------------------------- screens
if page is None:  # clicking the active segment deselects it; stay where we were
    page = st.session_state.get("last_page", "home")
st.session_state.last_page = page

if st.session_state.get("quiz") and ctx.me:
    page_quiz()
else:
    SCREENS[page]()
