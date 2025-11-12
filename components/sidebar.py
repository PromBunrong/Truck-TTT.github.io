# components/sidebar.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import date

def render_sidebar(default_date, refresh_interval_seconds):
    st.sidebar.title("Filters & Refresh")

    # Date picker default to last date found in sheet
    selected_date = st.sidebar.date_input("Select date", value=default_date)

    # Auto refresh
    auto_refresh = st.sidebar.checkbox("Auto refresh", value=True)
    # If auto refresh enabled, use st_autorefresh in main with given interval.

    # Manual refresh button
    manual_refresh = st.sidebar.button("Manual refresh")

    # Upload/Unload selector
    upload_type = st.sidebar.selectbox("Uploading / Unloading", options=["All", "Uploading", "Unloading"], index=0)

    # Product groups (multi)
    product_options = ["Pipe", "Coil", "Trading", "Roofing", "PU", "Other"]
    product_selected = st.sidebar.multiselect("Product Group", options=product_options, default=product_options)

    # compact info
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"Auto-refresh: ⏱️ {refresh_interval_seconds}s")
    # st.sidebar.markdown("Data source: Google Sheets")

    return {
        "selected_date": selected_date,
        "auto_refresh": auto_refresh,
        "manual_refresh": manual_refresh,
        "upload_type": None if upload_type == "All" else upload_type,
        "product_selected": product_selected
    }
