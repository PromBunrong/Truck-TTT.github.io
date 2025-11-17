# components/daily_performance.py
import streamlit as st
import pandas as pd
from data.metrics import compute_per_truck_metrics


def show_daily_performance(dfs, selected_date, product_selected, upload_type):
    """
    Corrected: properly merges Coming_to_load_or_Unload and Total_Weight_MT
    with per-truck KPI rows before aggregating by Product_Group and Coming_to_load_or_Unload.
    """

    df_security = dfs['security']
    df_logistic = dfs['logistic']
    df_status = dfs['status']
    df_driver = dfs['driver']

    # Compute per-truck durations (Total_min)
    df_kpi = compute_per_truck_metrics(
        df_security, df_status, df_logistic, df_driver,
        selected_date=selected_date,
        product_filter=product_selected,
        upload_type=upload_type,
        use_fallbacks=False
    )

    if df_kpi.empty:
        st.info("No data available for selected filters.")
        return

    # Ensure keys available
    if "Truck_Plate_Number" not in df_kpi.columns:
        st.error("Per-truck KPI missing Truck_Plate_Number.")
        return

    # Prepare coming-to-load (from security) mapped per truck
    if "Coming_to_Upload_or_Unload" in df_security.columns:
        sec_map = df_security.groupby("Truck_Plate_Number")["Coming_to_Upload_or_Unload"].agg("first").rename("Coming_to_load_or_Unload").reset_index()
    else:
        sec_map = pd.DataFrame(columns=["Truck_Plate_Number", "Coming_to_load_or_Unload"])

    # Prepare weight per truck from logistic (max or latest)
    if "Total_Weight_MT" in df_logistic.columns:
        weight_map = df_logistic.groupby("Truck_Plate_Number")["Total_Weight_MT"].agg("sum").rename("Total_Weight_MT").reset_index()
    else:
        weight_map = pd.DataFrame(columns=["Truck_Plate_Number", "Total_Weight_MT"])

    # Merge maps into kpi
    merged = df_kpi.merge(sec_map, on="Truck_Plate_Number", how="left")
    merged = merged.merge(weight_map, on="Truck_Plate_Number", how="left")

    # If selected_date provided ensure Date column is a date type
    if "Date" in merged.columns and selected_date is not None:
        merged = merged[pd.to_datetime(merged["Date"]).dt.date == selected_date]

    # Final aggregation grouped by Product_Group and Coming_to_load_or_Unload
    agg = merged.groupby(["Product_Group", "Coming_to_load_or_Unload"], dropna=False).agg(
        Total_truck=("Truck_Plate_Number", lambda s: s.nunique()),
        Total_weight_MT=("Total_Weight_MT", "sum"),
        Total_min=("Total_min", "sum")
    ).reset_index()

    # Compute Loading_Rate (min per MT). Avoid division by zero.
    def compute_rate(row):
        wt = row["Total_weight_MT"]
        tm = row["Total_min"]
        if pd.isna(wt) or wt == 0:
            return None
        if pd.isna(tm):
            return None
        return tm / wt

    agg["Loading_Rate"] = agg.apply(compute_rate, axis=1)

    st.subheader("Daily Performance by Product Group")
    if agg.empty:
        st.info("No daily performance data.")
    else:
        # reorder columns for clearer view
        cols = ["Product_Group", "Coming_to_load_or_Unload", "Total_truck", "Total_weight_MT", "Total_min", "Loading_Rate"]
        st.dataframe(agg[cols].sort_values(["Product_Group", "Coming_to_load_or_Unload"]).reset_index(drop=True), hide_index=True)

