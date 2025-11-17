# local_app.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd

from config.config import REFRESH_INTERVAL_SECONDS, DEBUG_MODE
from data.loader import load_all_sheets, get_current_date_from_sheets
from data.processor import clean_sheet_dfs
from components.sidebar import render_sidebar
from components.status_summary import show_status_summary
from components.current_waiting import show_current_waiting
from components.loading_durations_status import show_loading_durations_status
from components.daily_performance import show_daily_performance

# ----------------------------------------------------
# APP CONFIG
# ----------------------------------------------------
st.set_page_config(page_title="🚚 Truck Turnaround Live Dashboard — LOCAL", layout="wide")
st.title("🚚 Truck Turnaround Live Dashboard — LOCAL MODE")

# ----------------------------------------------------
# LOAD DATA
# ----------------------------------------------------
raw_dfs = load_all_sheets()
default_date = get_current_date_from_sheets(raw_dfs)

# ----------------------------------------------------
# FUNCTION: Safe Rerun
# ----------------------------------------------------import streamlit as st

def safe_rerun():
    """
    Try to rerun the Streamlit script in a robust way across Streamlit versions/environments:
      1. Preferred: st.experimental_rerun()
      2. Fallback: HTML meta refresh (reload page)
      3. Final fallback: st.stop() (stops execution — user can refresh)
    """
    # First attempt the official API (works in most environments)
    try:
        return st.experimental_rerun()
    except Exception as e:
        # If attribute missing or other runtime error, fall back gracefully
        # 1) Try meta refresh (forces browser to reload page)
        try:
            st.markdown("<meta http-equiv='refresh' content='0'>", unsafe_allow_html=True)
            return
        except Exception:
            pass
        # 2) Last resort: stop execution (user can manually refresh page)
        try:
            st.stop()
            return
        except Exception:
            # give up silently (nothing else we can do)
            return


# Sidebar setup (with refresh controls)
sb = render_sidebar(default_date, REFRESH_INTERVAL_SECONDS)

# ----------------------------------------------------
# AUTO REFRESH LOGIC (local version)
# ----------------------------------------------------
# Auto refresh if enabled
if sb["auto_refresh"]:
    st_autorefresh(interval=REFRESH_INTERVAL_SECONDS * 1000, key="autorefresh_local")

# Manual refresh button
if sb["manual_refresh"]:
    # clear cache(s)
    try:
        st.cache_data.clear()
    except Exception:
        try:
            # fallback for older Streamlit versions
            st.caching.clear_cache()
        except Exception:
            pass

    # robustly try to rerun / reload
    safe_rerun()


# ----------------------------------------------------
# CLEAN + PROCESS DATA
# ----------------------------------------------------
dfs = clean_sheet_dfs(raw_dfs)

# ----------------------------------------------------
# OPTIONAL DEBUG PANEL
# ----------------------------------------------------
if DEBUG_MODE:
    with st.sidebar.expander("Debug Panel", expanded=False):
        st.write("🕒 Local Time (Asia/Phnom_Penh):", pd.Timestamp.now(tz="Asia/Phnom_Penh"))
        st.write("Recent status records:")
        st.write(dfs['status'].sort_values("Timestamp").tail(10))
        st.write("Recent security records:")
        st.write(dfs['security'].sort_values("Timestamp").tail(10))
        st.caption("Debug mode is enabled only in LOCAL environment.")

# ----------------------------------------------------
# MAIN DASHBOARD SECTIONS
# ----------------------------------------------------
# 1️⃣ Status summary
show_status_summary(
    dfs['status'],
    product_filter=sb["product_selected"],
    upload_type=sb["upload_type"],
    selected_date=sb["selected_date"]
)
st.divider()

# 2️⃣ Current waiting trucks
show_current_waiting(
    dfs['security'], dfs['status'], dfs['driver'],
    product_filter=sb["product_selected"],
    upload_type=sb["upload_type"],
    selected_date=sb["selected_date"]
)
st.divider()

# 3️⃣ Loading durations table
show_loading_durations_status(
    dfs,
    selected_date=sb["selected_date"],
    product_selected=sb["product_selected"],
    upload_type=sb["upload_type"]
)
st.divider()

# 4️⃣ Daily performance
show_daily_performance(
    dfs,
    selected_date=sb["selected_date"],
    product_selected=sb["product_selected"],
    upload_type=sb["upload_type"]
)

# ----------------------------------------------------
# FOOTER
# ----------------------------------------------------
st.markdown("---")
st.caption("🔄 Auto-refresh every {} seconds (local mode)".format(REFRESH_INTERVAL_SECONDS))
if DEBUG_MODE:
    st.caption("🧑‍💻 Debug mode active — local testing environment.")
