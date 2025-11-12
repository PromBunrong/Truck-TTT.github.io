# host_app.py
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

st.set_page_config(page_title="🚚 Truck Turnaround Live Dashboard — HOSTED", layout="wide")
st.title("🚚 Truck Turnaround Live Dashboard — HOSTED")

raw_dfs = load_all_sheets()
default_date = get_current_date_from_sheets(raw_dfs)
sb = render_sidebar(default_date, REFRESH_INTERVAL_SECONDS)

# Auto refresh every 30s
if sb["auto_refresh"]:
    st_autorefresh(interval=REFRESH_INTERVAL_SECONDS * 1000, key="autorefresh")

# Manual refresh
if sb["manual_refresh"]:
    st.cache_data.clear()
    st.experimental_rerun()

dfs = clean_sheet_dfs(raw_dfs)

# Optional debug toggle (off by default)
if DEBUG_MODE:
    with st.sidebar.expander("Debug Info", expanded=False):
        st.write("Now (Asia/Phnom_Penh):", pd.Timestamp.now(tz="Asia/Phnom_Penh"))
        st.write(dfs['status'].sort_values("Timestamp").tail(10))

show_status_summary(dfs['status'], sb["product_selected"], sb["upload_type"], sb["selected_date"])
st.divider()

show_current_waiting(dfs['security'], dfs['status'], dfs['driver'],
                     sb["product_selected"], sb["upload_type"], sb["selected_date"])
st.divider()

show_loading_durations_status(dfs, sb["selected_date"], sb["product_selected"], sb["upload_type"])
st.divider()

show_daily_performance(dfs, sb["selected_date"], sb["product_selected"], sb["upload_type"])
