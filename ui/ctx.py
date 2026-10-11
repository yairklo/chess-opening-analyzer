"""Per-run context (selected player, filters, loaded data), stored in the session so that two browser sessions
never see each other's values. Screens read `ctx.fdf`, `ctx.probs`, ...; app.py sets them once per run."""
import streamlit as st


class _Ctx:
    def __getattr__(self, name):
        try:
            return st.session_state["_ctx"][name]
        except KeyError:
            raise AttributeError(name) from None

    def set(self, **values):
        st.session_state.setdefault("_ctx", {}).update(values)

    def has(self, name):
        return name in st.session_state.get("_ctx", {})


ctx = _Ctx()
