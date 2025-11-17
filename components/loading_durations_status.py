# components/loading_durations_status.py
import streamlit as st
import pandas as pd
from data.metrics import compute_per_truck_metrics

def _compute_mission(row):
    """Return mission status text based on existence of Start_Loading_Time and Completed_Time."""
    start = row.get("Start_Loading_Time")
    completed = row.get("Completed_Time")

    if pd.notna(completed):
        return "Done"
    missing_start = pd.isna(start)
    missing_completed = pd.isna(completed)

    if missing_start and missing_completed:
        return "Missing Start loading, completed"
    if missing_start:
        return "Missing Start Loading"
    if missing_completed:
        return "Missing Completed"
    return "Pending"  # fallback (shouldn't normally happen)

def show_loading_durations_status(dfs, selected_date, product_selected, upload_type):
    """
    Display Loading Durations Status with Total_Weight_MT, Loading_Rate and Mission.
    """
    df_security = dfs['security']
    df_status = dfs['status']
    df_logistic = dfs['logistic']
    df_driver = dfs['driver']

    # Compute core per-truck metrics (strict mode)
    df_kpi = compute_per_truck_metrics(
        df_security, df_status, df_logistic, df_driver,
        selected_date=selected_date,
        product_filter=product_selected,
        upload_type=upload_type,
        use_fallbacks=False
    )

    # If empty, show message
    if df_kpi.empty:
        st.subheader("Loading Durations Status")
        st.info("No duration data for selected filters.")
        return

    # Add Total_Weight_MT from logistic (sum or max depending on your rule; here sum)
    if "Truck_Plate_Number" in df_logistic.columns and "Total_Weight_MT" in df_logistic.columns:
        weight_map = df_logistic.groupby("Truck_Plate_Number")["Total_Weight_MT"].agg("sum")
        df_kpi = df_kpi.join(weight_map, on="Truck_Plate_Number")
    else:
        df_kpi["Total_Weight_MT"] = None

    # Compute Loading_Rate (Loading_min per MT)
    def compute_rate(r):
        try:
            lm = r.get("Loading_min")
            wt = r.get("Total_Weight_MT")
            if pd.isna(lm) or pd.isna(wt) or wt == 0:
                return None
            return lm / wt
        except Exception:
            return None

    df_kpi["Loading_Rate"] = df_kpi.apply(compute_rate, axis=1)

    # Add Mission column
    df_kpi["Mission"] = df_kpi.apply(_compute_mission, axis=1)

    # Reorder columns for display (adjust as you prefer)
    display_cols = [
        "Product_Group",
        "Truck_Plate_Number",
        "Date",
        "Arrival_Time",
        "Start_Loading_Time",
        "Completed_Time",
        "Waiting_min",
        "Loading_min",
        "Total_min",    
        "Total_Weight_MT",
        "Loading_Rate",
        "Mission",
        # "Data_Quality_Flag"  
    ]
    # keep only columns that exist
    display_cols = [c for c in display_cols if c in df_kpi.columns]

    st.subheader("Loading Durations Status")
    st.dataframe(df_kpi[display_cols].reset_index(drop=True).sort_values(["Product_Group", "Date", "Truck_Plate_Number"]).reset_index(drop=True), hide_index=True)
