# components/status_summary.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

def show_status_summary(df_status, product_filter=None, upload_type=None, selected_date=None, df_logistic=None, df_kpi=None):
    """
    Displays the count of trucks in each real-time status: Waiting, Start_Loading, Completed.
    Uses the *latest* status per truck+product combination to support multi-product visits.
    """

    if df_status.empty or "Truck_Plate_Number" not in df_status.columns:
        st.warning("No status data available.")
        return

    df_status["Timestamp"] = pd.to_datetime(df_status["Timestamp"], errors="coerce")

    # Keep the latest record per truck+product (for multi-product visits)
    if "Product_Group" in df_status.columns:
        df_latest = df_status.sort_values("Timestamp").groupby(["Truck_Plate_Number", "Product_Group"]).last().reset_index()
    else:
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

    # Layout: summary cards, gauge chart, and histogram
    left_col, middle_col, right_col = st.columns([2, 1, 1])
    with left_col:
        st.markdown(card_html, unsafe_allow_html=True)

    # Create gauge chart for completion progress
    # Calculate planned weight (from logistic) vs completed weight (from status + logistic)
    planned_weight = 0
    completed_weight = 0
    
    if df_logistic is not None and not df_logistic.empty:
        # Parse timestamp and filter by date if needed
        df_log = df_logistic.copy()
        if "Timestamp" in df_log.columns:
            df_log["Timestamp"] = pd.to_datetime(df_log["Timestamp"], errors="coerce")
            if selected_date:
                df_log["_Date"] = df_log["Timestamp"].dt.date
                df_log = df_log[df_log["_Date"] == selected_date]
        
        # Apply product filter if specified
        if product_filter and "Product_Group" in df_log.columns:
            df_log = df_log[df_log["Product_Group"].isin(product_filter)]
        
        # Calculate total planned weight from logistic sheet
        if "Total_Weight_MT" in df_log.columns:
            planned_weight = df_log["Total_Weight_MT"].sum()
        
        # Find completed trucks from status
        if not df_status.empty:
            df_stat = df_status.copy()
            df_stat["Timestamp"] = pd.to_datetime(df_stat["Timestamp"], errors="coerce")
            
            # Get latest status per truck
            df_stat_latest = df_stat.sort_values("Timestamp").groupby("Truck_Plate_Number").last().reset_index()
            
            # Apply filters
            if product_filter and "Product_Group" in df_stat_latest.columns:
                df_stat_latest = df_stat_latest[df_stat_latest["Product_Group"].isin(product_filter)]
            if selected_date:
                df_stat_latest["_Date"] = df_stat_latest["Timestamp"].dt.date
                df_stat_latest = df_stat_latest[df_stat_latest["_Date"] == selected_date]
            
            # Get completed trucks
            completed_trucks = df_stat_latest[df_stat_latest["Status"] == "Completed"]["Truck_Plate_Number"].unique()
            
            # Sum weight for completed trucks from logistic
            if "Truck_Plate_Number" in df_log.columns and len(completed_trucks) > 0:
                completed_weight = df_log[df_log["Truck_Plate_Number"].isin(completed_trucks)]["Total_Weight_MT"].sum()
    
    # Calculate completion percentage
    completion_pct = 0
    if planned_weight > 0:
        completion_pct = min((completed_weight / planned_weight) * 100, 100)
    
    # Create gauge chart
    gauge_fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=completion_pct,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "Completion", 'font': {'size': 14}},
        delta={'reference': 100, 'suffix': '%'},
        number={'suffix': '%', 'font': {'size': 20}},
        gauge={
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkgray"},
            'bar': {'color': "#10b981"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 50], 'color': '#fee2e2'},
                {'range': [50, 80], 'color': '#fef3c7'},
                {'range': [80, 100], 'color': '#d1fae5'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 95
            }
        }
    ))
    
    gauge_fig.update_layout(
        width=200,
        height=150,
        margin=dict(l=10, r=10, t=40, b=5),
        paper_bgcolor="white",
        font={'color': "darkgray", 'family': "Arial"}
    )
    
    with middle_col:
        st.plotly_chart(gauge_fig, use_container_width=True)
        # Show weight details below gauge chart
        st.markdown(f"<div style='text-align: center; margin-top: -15px; font-size: 0.85em;'>📦 Planned: {planned_weight:.1f} MT<br/>✅ Completed: {completed_weight:.1f} MT</div>", unsafe_allow_html=True)

    # Create histogram for Loading_Rate_min/MT by product group
    if df_kpi is not None and not df_kpi.empty and df_logistic is not None:
        df_hist = df_kpi.copy()
        
        # Merge Total_Weight_MT from logistic if not present
        if "Total_Weight_MT" not in df_hist.columns:
            df_log = df_logistic.copy()
            if "Timestamp" in df_log.columns:
                df_log["Timestamp"] = pd.to_datetime(df_log["Timestamp"], errors="coerce")
                df_log["_Date"] = df_log["Timestamp"].dt.date
            else:
                df_log["_Date"] = None
            
            if "Product_Group" in df_log.columns and "Truck_Plate_Number" in df_log.columns:
                weight_map = (
                    df_log.groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Total_Weight_MT"]
                    .sum()
                    .reset_index()
                    .rename(columns={"_Date": "Date"})
                )
                
                # Ensure Date column in df_hist
                if "Date" not in df_hist.columns and "Arrival_Time" in df_hist.columns:
                    df_hist["Date"] = pd.to_datetime(df_hist["Arrival_Time"], errors="coerce").dt.date
                
                df_hist = df_hist.merge(weight_map, on=["Truck_Plate_Number", "Product_Group", "Date"], how="left")
        
        # Calculate Loading_Rate_min/MT (same logic as loading_durations_status.py)
        def calc_rate(row):
            loading = row.get("Loading_min")
            weight = row.get("Total_Weight_MT")
            if pd.notna(loading) and pd.notna(weight) and weight > 0:
                return loading / weight
            return None
        
        df_hist["Loading_Rate_min/MT"] = df_hist.apply(calc_rate, axis=1)
        
        # Filter for valid data
        df_hist = df_hist[df_hist["Loading_Rate_min/MT"].notna()]
        
        if not df_hist.empty and "Product_Group" in df_hist.columns:
            # Create histogram
            hist_fig = px.histogram(
                df_hist,
                x="Loading_Rate_min/MT",
                color="Product_Group",
                nbins=20,
                title="Loading Rate Distribution",
                labels={"Loading_Rate_min/MT": "Loading Rate (min/MT)"},
                barmode="overlay",
                opacity=0.7
            )
            
            hist_fig.update_layout(
                width=220,
                height=150,
                margin=dict(l=10, r=10, t=40, b=20),
                paper_bgcolor="white",
                font={'size': 10},
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.5,
                    xanchor="center",
                    x=0.5,
                    font={'size': 8}
                ),
                xaxis={'title': {'font': {'size': 10}}},
                yaxis={'title': {'text': 'Count', 'font': {'size': 10}}}
            )
            
            with right_col:
                st.plotly_chart(hist_fig, use_container_width=True)
        else:
            with right_col:
                st.info("No loading rate data")
    else:
        with right_col:
            st.info("No data available")
