# components/daily_performance.py
import streamlit as st
import pandas as pd
from data.metrics import compute_per_truck_metrics


def show_daily_performance(dfs, selected_date=None, start_date=None, end_date=None, product_selected=None, upload_type=None):
    """
    Daily performance aggregated by (Product_Group, Coming_to_load_or_Unload).
    Correct weight logic: Total_Weight_MT aggregated PER Truck + Product_Group + Date.
    Supports both single date and date range filtering.
    """

    df_security = dfs['security']
    df_logistic = dfs['logistic']
    df_status = dfs['status']
    df_driver = dfs['driver']

    # --- Step 1: Compute per-truck KPI rows (Arrival, Start, Completed, durations, Date)
    df_kpi = compute_per_truck_metrics(
        df_security,
        df_status,
        df_logistic,
        df_driver,
        selected_date=selected_date,
        start_date=start_date,
        end_date=end_date,
        product_filter=product_selected,
        upload_type=upload_type,
        use_fallbacks=False
    )

    if df_kpi.empty:
        st.subheader("Daily Performance by Product Group")
        st.info("No daily performance data.")
        return

    # Ensure Date column is date type
    if "Date" in df_kpi.columns:
        df_kpi["Date"] = pd.to_datetime(df_kpi["Date"], errors="coerce").dt.date

    # ---------------------------------------------------------------------
    # --- Step 2: Build logistic weight map per truck + product + date ---
    # ---------------------------------------------------------------------
    if "Timestamp" in df_logistic.columns:
        df_logistic["Timestamp"] = pd.to_datetime(df_logistic["Timestamp"], errors="coerce")
        df_logistic["_Date"] = df_logistic["Timestamp"].dt.date
    else:
        df_logistic["_Date"] = None

    if "Product_Group" not in df_logistic.columns:
        df_logistic["Product_Group"] = None

    # Correct weight mapping - check if Total_Weight_MT exists
    if "Total_Weight_MT" in df_logistic.columns:
        weight_map = (
            df_logistic.groupby(
                ["Truck_Plate_Number", "Product_Group", "_Date"],
                dropna=False
            )["Total_Weight_MT"]
            .sum()
            .reset_index()
            .rename(columns={"_Date": "Date"})
        )

        # Merge weight map into KPI
        df_kpi = df_kpi.merge(
            weight_map,
            on=["Truck_Plate_Number", "Product_Group", "Date"],
            how="left"
        )

    # If weight missing → None
    if "Total_Weight_MT" not in df_kpi.columns:
        df_kpi["Total_Weight_MT"] = None

    # ---------------------------------------------------------------------
    # --- Step 3: Attach Coming_to_Load_or_Unload from Security (date-range based) ---
    # Use simpler date-range filtering instead of complex timestamp matching
    # ---------------------------------------------------------------------
    
    if "Coming_to_Load_or_Unload" in df_security.columns and "Timestamp" in df_security.columns:
        df_security_dated = df_security.copy()
        df_security_dated["Timestamp"] = pd.to_datetime(df_security_dated["Timestamp"], errors="coerce")
        df_security_dated["_Date"] = df_security_dated["Timestamp"].dt.date
        
        # Filter security records to selected date range
        if selected_date is not None:
            sec_filtered = df_security_dated[df_security_dated["_Date"] == selected_date]
        elif start_date is not None or end_date is not None:
            if start_date and end_date:
                sec_filtered = df_security_dated[(df_security_dated["_Date"] >= start_date) & (df_security_dated["_Date"] <= end_date)]
            elif start_date:
                sec_filtered = df_security_dated[df_security_dated["_Date"] >= start_date]
            else:
                sec_filtered = df_security_dated[df_security_dated["_Date"] <= end_date]
        else:
            sec_filtered = df_security_dated.copy()
        
        # Get first Coming_to_Load_or_Unload per truck+date within date range
        if not sec_filtered.empty and "Truck_Plate_Number" in sec_filtered.columns:
            sec_map = (
                sec_filtered.sort_values("Timestamp")
                .groupby(["Truck_Plate_Number", "_Date"])["Coming_to_Load_or_Unload"]
                .first()
                .reset_index()
                .rename(columns={"_Date": "Date"})
            )
            df_kpi = df_kpi.merge(sec_map, on=["Truck_Plate_Number", "Date"], how="left")
        else:
            df_kpi["Coming_to_Load_or_Unload"] = None
        
        # Replace NaN with alert message
        df_kpi["Coming_to_Load_or_Unload"] = df_kpi["Coming_to_Load_or_Unload"].fillna("⚠️ NO SECURITY RECORD")
    else:
        df_kpi["Coming_to_Load_or_Unload"] = None

    # ---------------------------------------------------------------------
    # --- Step 4: Compute Loading_Rate (Total_min per MT) ---
    # ---------------------------------------------------------------------
    def compute_rate(row):
        wt = row.get("Total_Weight_MT")
        tm = row.get("Total_min")
        if pd.isna(wt) or wt == 0:
            return None
        if pd.isna(tm):
            return None
        return tm / wt

    df_kpi["Loading_Rate"] = df_kpi.apply(compute_rate, axis=1)

    # ---------------------------------------------------------------------
    # --- Step 5: Aggregate for Daily Performance ---
    # ---------------------------------------------------------------------
    agg = df_kpi.groupby(
        ["Product_Group", "Coming_to_Load_or_Unload"],
        dropna=False
    ).agg(
        Total_truck=("Truck_Plate_Number", lambda s: s.nunique()),
        Total_weight_MT=("Total_Weight_MT", "sum"),
        Total_Loading_min=("Loading_min", "sum")
    ).reset_index()

    # Compute daily aggregated Loading Rate
    def compute_rate_daily(row):
        wt = row["Total_weight_MT"]
        lm = row["Total_Loading_min"]
        if pd.isna(wt) or wt == 0:
            return None
        if pd.isna(lm):
            return None
        return lm / wt

    agg["Loading_Rate_min/MT"] = agg.apply(compute_rate_daily, axis=1)
    
    # Compute MT/Hour rate
    def compute_mt_per_hour_daily(row):
        wt = row["Total_weight_MT"]
        lm = row["Total_Loading_min"]
        if pd.isna(wt) or pd.isna(lm) or lm == 0:
            return None
        return (float(wt) * 60.0) / float(lm)
    
    agg["Loading_Rate_MT/Hour"] = agg.apply(compute_mt_per_hour_daily, axis=1)
    
    # Round rates to 2 decimal places
    for col in ["Loading_Rate_min/MT", "Loading_Rate_MT/Hour", "Total_weight_MT", "Total_Loading_min"]:
        if col in agg.columns:
            agg[col] = pd.to_numeric(agg[col], errors="coerce").round(2)

    # ---------------------------------------------------------------------
    # --- Filter by upload_type after aggregation ---
    # ---------------------------------------------------------------------
    if upload_type:
        agg = agg[agg["Coming_to_Load_or_Unload"] == upload_type]

    # ---------------------------------------------------------------------
    # --- Step 6: Display ---
    # ---------------------------------------------------------------------
    st.subheader("Loading Performance by Product Group")

    if agg.empty:
        st.info("No daily performance data.")
        return

    # Order columns
    cols = [
        "Product_Group",
        "Coming_to_Load_or_Unload",
        "Total_truck",
        "Total_weight_MT",
        "Total_Loading_min",
        "Loading_Rate_min/MT",
        "Loading_Rate_MT/Hour"
    ]

    # Sort and display
    df_view = agg[cols].sort_values(["Product_Group", "Coming_to_Load_or_Unload"]).reset_index(drop=True)
    st.dataframe(df_view, hide_index=True, use_container_width=True)
