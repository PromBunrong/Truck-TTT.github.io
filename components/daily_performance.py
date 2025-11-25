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
    # --- Step 3: Attach Coming_to_load_or_Unload from Security (date-aware) ---
    # Prefer security records that occurred on the selected_date; fallback to first-known overall
    # ---------------------------------------------------------------------
    if "Coming_to_Load_or_Unload" in df_security.columns and "Timestamp" in df_security.columns:
        # parse Timestamp and compute date
        df_security = df_security.copy()
        df_security["Timestamp"] = pd.to_datetime(df_security["Timestamp"], errors="coerce")
        df_security["_Date"] = df_security["Timestamp"].dt.date

        if selected_date is not None:
            # use records on that date first
            sec_for_date = df_security[df_security["_Date"] == selected_date].sort_values("Timestamp")
            sec_map_date = sec_for_date.groupby("Truck_Plate_Number")["Coming_to_Load_or_Unload"].agg("first").rename("Coming_to_load_or_Unload").reset_index()
        else:
            sec_map_date = pd.DataFrame(columns=["Truck_Plate_Number", "Coming_to_load_or_Unload"])

        # fallback map from full history (first-known)
        sec_map_hist = df_security.sort_values("Timestamp").groupby("Truck_Plate_Number")["Coming_to_Load_or_Unload"].agg("first").rename("Coming_to_load_or_Unload").reset_index()

        # merge date-specific map first, then fill missing from history
        if not sec_map_date.empty:
            df_kpi = df_kpi.merge(sec_map_date, on="Truck_Plate_Number", how="left")
            # find trucks missing date-specific entry and fill from history
            missing = df_kpi["Coming_to_load_or_Unload"].isna()
            if missing.any():
                df_kpi = df_kpi.merge(sec_map_hist, on="Truck_Plate_Number", how="left", suffixes=("", "_hist"))
                df_kpi["Coming_to_load_or_Unload"] = df_kpi["Coming_to_load_or_Unload"].fillna(df_kpi.get("Coming_to_load_or_Unload_hist"))
                df_kpi = df_kpi.drop(columns=[c for c in df_kpi.columns if c.endswith("_hist")])
        else:
            df_kpi = df_kpi.merge(sec_map_hist, on="Truck_Plate_Number", how="left")

    else:
        df_kpi = df_kpi.assign(Coming_to_load_or_Unload=None)

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
        ["Product_Group", "Coming_to_load_or_Unload"],
        dropna=False
    ).agg(
        Total_truck=("Truck_Plate_Number", lambda s: s.nunique()),
        Total_weight_MT=("Total_Weight_MT", "sum"),
        Total_min=("Total_min", "sum")
    ).reset_index()

    # Compute daily aggregated Loading Rate
    def compute_rate_daily(row):
        wt = row["Total_weight_MT"]
        tm = row["Total_min"]
        if pd.isna(wt) or wt == 0:
            return None
        if pd.isna(tm):
            return None
        return tm / wt

    agg["Loading_Rate"] = agg.apply(compute_rate_daily, axis=1)

    # ---------------------------------------------------------------------
    # --- Step 6: Display ---
    # ---------------------------------------------------------------------
    st.subheader("Daily Performance by Product Group")

    if agg.empty:
        st.info("No daily performance data.")
        return

    # Order columns
    cols = [
        "Product_Group",
        "Coming_to_load_or_Unload",
        "Total_truck",
        "Total_weight_MT",
        "Total_min",
        "Loading_Rate"
    ]

    # Sort and display
    df_view = agg[cols].sort_values(["Product_Group", "Coming_to_load_or_Unload"]).reset_index(drop=True)
    n_rows = len(df_view)
    if n_rows > 5:
        row_h = 40
        header_h = 40
        height = header_h + row_h * 5
        st.dataframe(df_view, hide_index=True, height=height)
    else:
        st.dataframe(df_view, hide_index=True)
