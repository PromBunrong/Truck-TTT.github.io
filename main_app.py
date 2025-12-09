# main_app.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd

# ---------------- CONFIG IMPORTS ----------------
from config.config import REFRESH_INTERVAL_SECONDS, DEBUG_MODE
from data.loader import load_all_sheets, get_current_date_from_sheets
from data.processor import clean_sheet_dfs

# ---------------- COMPONENT IMPORTS ----------------
from components.sidebar import render_sidebar
from components.status_summary import show_status_summary
from components.current_waiting import show_current_waiting
from components.loading_durations_status import show_loading_durations_status
from components.daily_performance import show_daily_performance
from components.styles import inject_styles


# ----------------------------------------------------
# APP CONFIG
# ----------------------------------------------------
st.set_page_config(page_title="🚚 Truck Turnaround Live Dashboard — HOSTED", layout="wide")
# Inject local CSS (if present) to compact spacing
try:
    inject_styles()
except Exception:
    pass

st.title("🚚 Truck Turnaround Live Dashboard")

# ----------------------------------------------------
# LOAD DATA
# ----------------------------------------------------
raw_dfs = load_all_sheets()
default_date = get_current_date_from_sheets(raw_dfs)

# ----------------------------------------------------
# FUNCTION: Safe Rerun
# ----------------------------------------------------
def safe_rerun():
    """
    Try to rerun the Streamlit script in a robust way across Streamlit versions/environments:
      1. Preferred: st.experimental_rerun()
      2. Fallback: HTML meta refresh (reload page)
      3. Final fallback: st.stop() (stops execution — user can refresh)
    """
    try:
        return st.experimental_rerun()
    except Exception:
        # Fallback 1: meta refresh in browser
        try:
            st.markdown("<meta http-equiv='refresh' content='0'>", unsafe_allow_html=True)
            return
        except Exception:
            pass
        # Fallback 2: stop execution
        try:
            st.stop()
            return
        except Exception:
            return


# ----------------------------------------------------
# SIDEBAR
# ----------------------------------------------------
sb = render_sidebar(default_date, REFRESH_INTERVAL_SECONDS)

# ----------------------------------------------------
# AUTO REFRESH LOGIC
# ----------------------------------------------------
# Auto refresh every n seconds
if sb["auto_refresh"]:
    st_autorefresh(interval=REFRESH_INTERVAL_SECONDS * 1000, key="autorefresh_host")

# Manual refresh button
if sb["manual_refresh"]:
    st.info("Refreshing data...")
    try:
        st.cache_data.clear()
    except Exception:
        try:
            st.caching.clear_cache()
        except Exception:
            pass
    safe_rerun()


# ----------------------------------------------------
# CLEAN + PROCESS DATA
# ----------------------------------------------------
dfs = clean_sheet_dfs(raw_dfs)

# ----------------------------------------------------
# DEBUG PANEL (Optional)
# ----------------------------------------------------
if DEBUG_MODE:
    with st.sidebar.expander("Debug / Host Check", expanded=False):
        st.write("🌐 Server Time (Asia/Phnom_Penh):", pd.Timestamp.now(tz="Asia/Phnom_Penh"))
        st.write("Recent Status Records:")
        st.write(dfs['status'].sort_values("Timestamp").tail(10))
        st.write("Recent Security Records:")
        st.write(dfs['security'].sort_values("Timestamp").tail(10))
        st.caption("Debug mode active (for host).")

# ----------------------------------------------------
# MAIN DASHBOARD SECTIONS
# ----------------------------------------------------
# Compute KPI metrics once for use in multiple sections
from data.metrics import compute_per_truck_metrics
df_kpi = compute_per_truck_metrics(
    dfs['security'], dfs['status'], dfs['logistic'], dfs['driver'],
    start_date=sb["start_date"],
    end_date=sb["end_date"],
    product_filter=sb["product_selected"],
    upload_type=sb["upload_type"],
    use_fallbacks=False
)

# 1️⃣ STATUS SUMMARY
show_status_summary(
    dfs['status'],
    df_security=dfs['security'],
    product_filter=sb["product_selected"],
    upload_type=sb["upload_type"],
    start_date=sb["start_date"],
    end_date=sb["end_date"],
    df_logistic=dfs.get('logistic'),
    df_kpi=df_kpi
)
st.divider()

# 2️⃣ CURRENT WAITING TRUCKS
show_current_waiting(
    dfs['security'], dfs['status'], dfs['driver'], dfs.get('logistic'),
    product_filter=sb["product_selected"],
    upload_type=sb["upload_type"],
    truck_condition=sb["truck_condition"],
    start_date=sb["start_date"],
    end_date=sb["end_date"]
)
st.divider()

# 3️⃣ LOADING DURATIONS TABLE
show_loading_durations_status(
    dfs,
    start_date=sb["start_date"],
    end_date=sb["end_date"],
    product_selected=sb["product_selected"],
    upload_type=sb["upload_type"],
    truck_condition=sb["truck_condition"]
)
st.divider()

# 4️⃣ DAILY PERFORMANCE
show_daily_performance(
    dfs,
    start_date=sb["start_date"],
    end_date=sb["end_date"],
    product_selected=sb["product_selected"],
    upload_type=sb["upload_type"]
)

# ----------------------------------------------------
# FOOTER
# ----------------------------------------------------
st.markdown("---")
st.caption(f"🔄 Auto-refresh every {REFRESH_INTERVAL_SECONDS} seconds (host mode).")
if DEBUG_MODE:
    st.caption("🧑‍💻 Debug mode active — hosting environment.")
