# components/status_summary.py
import streamlit as st
import pandas as pd

def show_status_summary(df_status, product_filter=None, upload_type=None, selected_date=None):
    """
    Displays the count of trucks in each real-time status: Waiting, Start_Loading, Completed.
    Uses the *latest* status per truck.
    """

    if df_status.empty or "Truck_Plate_Number" not in df_status.columns:
        st.warning("No status data available.")
        return

    df_status["Timestamp"] = pd.to_datetime(df_status["Timestamp"], errors="coerce")

    # Keep the latest record per truck
    df_latest = df_status.sort_values("Timestamp").groupby("Truck_Plate_Number").last().reset_index()

    # Optional filters
    if product_filter:
        df_latest = df_latest[df_latest["Product_Group"].isin(product_filter)]
    if selected_date:
        df_latest = df_latest[pd.to_datetime(df_latest["Timestamp"]).dt.date == selected_date]

    # Count each status
    waiting_count = df_latest[df_latest["Status"] == "Arrival"].shape[0]
    start_count = df_latest[df_latest["Status"] == "Start_Loading"].shape[0]
    completed_count = df_latest[df_latest["Status"] == "Completed"].shape[0]

    # Show metrics in columns
    col1, col2, col3 = st.columns(3)
    col1.metric("🕒 Waiting", waiting_count)
    col2.metric("⚙️ Start Loading", start_count)
    col3.metric("✅ Completed", completed_count)
