# components/daily_performance.py
import streamlit as st
import pandas as pd
from data.metrics import compute_per_truck_metrics


def show_daily_performance(dfs, selected_date, product_selected, upload_type):
    """
    Daily performance aggregated by (Product_Group, Coming_to_load_or_Unload).
    Correct weight logic: Total_Weight_MT aggregated PER Truck + Product_Group + Date.
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

    # Correct weight mapping
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
    # --- Step 3: Attach Coming_to_Load_or_Unload from Security (date-aware) ---
    # WORKAROUND: Security sheet has corrupted truck plates (0.00E+00, etc)
    # Strategy: Use Status sheet truck plates and match by date to get the action from Security
    # ---------------------------------------------------------------------
    
    # First, try to build a mapping from Status truck plates to Security actions by matching on date
    if "Coming_to_Load_or_Unload" in df_security.columns and "Timestamp" in df_security.columns and "Timestamp" in df_status.columns:
        df_security = df_security.copy()
        df_status_copy = df_status.copy()
        
        # Parse timestamps and extract dates
        df_security["Timestamp"] = pd.to_datetime(df_security["Timestamp"], errors="coerce")
        df_security["_Date"] = df_security["Timestamp"].dt.date
        df_status_copy["Timestamp"] = pd.to_datetime(df_status_copy["Timestamp"], errors="coerce")
        df_status_copy["_Date"] = df_status_copy["Timestamp"].dt.date
        
        # Get the earliest status event per truck per date (this tells us when they arrived)
        if "Truck_Plate_Number" in df_status_copy.columns:
            status_first = df_status_copy.sort_values("Timestamp").groupby(["Truck_Plate_Number", "_Date"]).agg({
                "Timestamp": "first"
            }).reset_index()
            status_first = status_first.rename(columns={"Timestamp": "Status_First_Time"})
            
            # For each status entry, find the closest Security entry on that date (within 30 min window)
            # and assume that's the gate entry
            security_with_action = df_security[["_Date", "Timestamp", "Coming_to_Load_or_Unload"]].copy()
            
            truck_to_action = {}
            match_stats = {"total": 0, "matched": 0, "no_security": 0, "no_action": 0, "too_far": 0}
            
            for _, row in status_first.iterrows():
                truck = row["Truck_Plate_Number"]
                date = row["_Date"]
                status_time = row["Status_First_Time"]
                match_stats["total"] += 1
                
                # Find security entries on that date within +/- 60 minutes of first status (increased from 30)
                sec_on_date = security_with_action[security_with_action["_Date"] == date].copy()
                if not sec_on_date.empty and pd.notna(status_time):
                    sec_on_date["time_diff"] = (sec_on_date["Timestamp"] - status_time).abs()
                    closest = sec_on_date.nsmallest(1, "time_diff")
                    if not closest.empty:
                        time_diff = closest.iloc[0]["time_diff"]
                        if time_diff <= pd.Timedelta(minutes=60):
                            action = closest.iloc[0]["Coming_to_Load_or_Unload"]
                            if pd.notna(action):
                                truck_to_action[(truck, date)] = action
                                match_stats["matched"] += 1
                            else:
                                match_stats["no_action"] += 1
                        else:
                            match_stats["too_far"] += 1
                else:
                    match_stats["no_security"] += 1
            
            # Apply this mapping to df_kpi
            def get_action(row):
                truck = row.get("Truck_Plate_Number")
                date = row.get("Date")
                return truck_to_action.get((truck, date), None)
            
            df_kpi["Coming_to_Load_or_Unload"] = df_kpi.apply(get_action, axis=1)
        else:
            df_kpi["Coming_to_Load_or_Unload"] = None
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
    n_rows = len(df_view)
    if n_rows > 5:
        row_h = 40
        header_h = 40
        height = header_h + row_h * 5
        st.dataframe(df_view, hide_index=True, height=height)
    else:
        st.dataframe(df_view, hide_index=True)
