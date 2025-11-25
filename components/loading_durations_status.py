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
    Total_Weight_MT is aggregated per (Truck_Plate_Number, Product_Group, Date)
    to avoid summing weights across product groups or dates.
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

    # Ensure Date column in df_kpi is date type (not datetime)
    if "Date" in df_kpi.columns:
        df_kpi["Date"] = pd.to_datetime(df_kpi["Date"], errors="coerce").dt.date

    # Prepare logistic weight map:
    # Need df_logistic to have Timestamp parsed and Date extracted
    weight_map = None
    if "Total_Weight_MT" in df_logistic.columns and "Truck_Plate_Number" in df_logistic.columns:
        # Parse Timestamp if present
        if "Timestamp" in df_logistic.columns:
            df_logistic["Timestamp"] = pd.to_datetime(df_logistic["Timestamp"], errors="coerce")
            df_logistic["_Date"] = df_logistic["Timestamp"].dt.date
        else:
            # If no Timestamp, try to rely on df_kpi Date by assuming weights apply to same day
            df_logistic["_Date"] = None

        # Ensure Product_Group exists in logistic
        if "Product_Group" in df_logistic.columns:
            # Sum weights per Truck + Product + Date
            # If _Date is None (no timestamp), group with NaN Date and later merge won't match by date.
            weight_map = (
                df_logistic
                .groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Total_Weight_MT"]
                .sum()
                .reset_index()
                .rename(columns={"_Date": "Date"})
            )
            # Convert Date column to date dtype (may contain None)
            if weight_map["Date"].isnull().any():
                # keep NaNs as-is
                weight_map["Date"] = weight_map["Date"].where(~weight_map["Date"].isnull(), None)
        else:
            weight_map = None

    # Merge weight_map into df_kpi using Truck_Plate_Number + Product_Group + Date
    if weight_map is not None:
        # if df_kpi has no Date column, we cannot merge by Date properly; ensure existence
        if "Date" not in df_kpi.columns:
            df_kpi["Date"] = None
        # Merge - left join so kpi rows keep their identity
        df_kpi = df_kpi.merge(
            weight_map,
            on=["Truck_Plate_Number", "Product_Group", "Date"],
            how="left"
        )
        # If Total_Weight_MT missing after merge, set to NaN
        if "Total_Weight_MT" not in df_kpi.columns:
            df_kpi["Total_Weight_MT"] = None
    else:
        # No logistic data to map, create column
        df_kpi["Total_Weight_MT"] = None

    # Compute Loading_Rate (min/MT) safely
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
    ]
    display_cols = [c for c in display_cols if c in df_kpi.columns]

    # --- Format timestamp columns to show ONLY time (if datetime)
    time_cols = ["Arrival_Time", "Start_Loading_Time", "Completed_Time"]
    for c in time_cols:
        if c in df_kpi.columns:
            # convert tz-aware datetimes safely, then format
            df_kpi[c] = pd.to_datetime(df_kpi[c], errors="coerce").dt.time.apply(lambda t: t.strftime("%H:%M:%S") if pd.notna(t) else None)

    st.subheader("Loading Durations Status")
    # Sort and display, hide index
    st.dataframe(
        df_kpi[display_cols]
        .sort_values(["Product_Group", "Date", "Truck_Plate_Number"])
        .reset_index(drop=True),
        hide_index=True
    )
