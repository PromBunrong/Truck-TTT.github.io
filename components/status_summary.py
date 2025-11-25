# components/status_summary.py
import streamlit as st
import pandas as pd
import plotly.express as px

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

    # Count each status (use 0 defaults)
    waiting_count = int(df_latest[df_latest["Status"] == "Arrival"].shape[0]) if not df_latest.empty else 0
    start_count = int(df_latest[df_latest["Status"] == "Start_Loading"].shape[0]) if not df_latest.empty else 0
    completed_count = int(df_latest[df_latest["Status"] == "Completed"].shape[0]) if not df_latest.empty else 0

    # Render compact summary cards using small custom HTML (styled via assets/styles.css)
    card_html = f"""
<div class="summary-cards">
    <div class="summary-card waiting">
        <div class="summary-label">🕒 Waiting</div>
        <div class="summary-number">{waiting_count}</div>
        <div class="summary-extra">Current trucks waiting to start loading</div>
    </div>
    <div class="summary-card start-loading">
        <div class="summary-label">⚙️ Start Loading</div>
        <div class="summary-number">{start_count}</div>
        <div class="summary-extra">Trucks currently in start loading</div>
    </div>
    <div class="summary-card completed">
        <div class="summary-label">✅ Completed</div>
        <div class="summary-number">{completed_count}</div>
        <div class="summary-extra">Trucks completed today</div>
    </div>
</div>
"""

    # Layout: summary cards on the left, donut chart on the right
    left_col, right_col = st.columns([2, 1])
    with left_col:
        st.markdown(card_html, unsafe_allow_html=True)

    # Create donut chart using Plotly
    counts = pd.DataFrame({
        "Status": ["Waiting", "Start Loading", "Completed"],
        "Count": [waiting_count, start_count, completed_count]
    })
    # Only draw if any counts
    if counts["Count"].sum() > 0:
        fig = px.pie(counts, names="Status", values="Count", hole=0.55,
                     color="Status",
                     color_discrete_map={"Waiting": "#ef4444", "Start Loading": "#3b82f6", "Completed": "#10b981"})
        fig.update_traces(textinfo="percent+label", marker=dict(line=dict(color="#FFFFFF", width=1)))
        # Make the donut compact to visually match the summary cards
        fig.update_layout(width=220, height=140, margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=-0.15))
        with right_col:
            # Render with fixed size (not container width) so it stays small
            st.plotly_chart(fig, use_container_width=False)
    else:
        with right_col:
            st.info("No status counts to display.")
