import streamlit as st
from pathlib import Path

def inject_styles(path: str = "assets/styles.css") -> bool:
    """Inject local CSS from `assets/styles.css` into the Streamlit app.

    Returns True if CSS was injected, False if file not found.
    """
    p = Path(path)
    if not p.exists():
        return False
    try:
        css = p.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
        return True
    except Exception:
        return False
