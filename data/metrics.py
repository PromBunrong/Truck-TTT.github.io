# data/metrics.py
import pandas as pd
import numpy as np
from config.config import LOCAL_TZ

def _safe_min(series):
    s = series.dropna()
    return s.min() if not s.empty else pd.NaT

def _safe_max(series):
    s = series.dropna()
    return s.max() if not s.empty else pd.NaT

def compute_per_truck_metrics(
    df_security,
    df_status,
    df_logistic,
    df_driver,
    selected_date=None,
    product_filter=None,
    upload_type=None,
    use_fallbacks=False
):
    """
    Compute per-truck arrival/start/completed and durations.
    If selected_date is provided (a date object), only events that occurred on that date
    are used to compute Arrival/Start/Completed for the per-truck metrics. This avoids
    old historical rows for the same truck plate interfering with today's metrics.
    """

    # Ensure Timestamp exists and is datetime
    for df in (df_security, df_status, df_logistic, df_driver):
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
            # if tz-naive, keep as-is (processor should handle tz), but ensure consistent dtype
            # If tz-aware, convert to local tz for date extraction
            try:
                if df["Timestamp"].dt.tz is not None:
                    df["Timestamp"] = df["Timestamp"].dt.tz_convert(LOCAL_TZ)
            except Exception:
                pass

    # If selected_date provided, filter status & logistic rows to that date for event selection
    def _filter_by_date(df, date):
        if date is None:
            return df.copy()
        if "Timestamp" not in df.columns:
            return df.iloc[0:0].copy()  # empty
        # normalize to LOCAL_TZ date
        ts = pd.to_datetime(df["Timestamp"], errors="coerce")
        # If tz-aware, convert; if naive, treat as local
        try:
            if ts.dt.tz is not None:
                dates = ts.dt.tz_convert(LOCAL_TZ).dt.date
            else:
                dates = ts.dt.date
        except Exception:
            dates = ts.dt.date
        return df[dates == date].copy()

    status_for_date = _filter_by_date(df_status, selected_date)
    logistic_for_date = _filter_by_date(df_logistic, selected_date)
    security_for_date = _filter_by_date(df_security, selected_date)
    driver_for_date = _filter_by_date(df_driver, selected_date)

    # ---- Compute primary events using rows FROM THE SELECTED DATE only ----
    # Arrival: earliest Arrival event on that date
    arrival = status_for_date[status_for_date["Status"] == "Arrival"].groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("Arrival_Time")

    # Start loading: earliest Start_Loading event on that date
    start_loading = status_for_date[status_for_date["Status"] == "Start_Loading"].groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("Start_Loading_Time")

    # Completed events on that date (keep list)
    completed_all = status_for_date[status_for_date["Status"] == "Completed"].copy()
    completed_grouped = completed_all.groupby("Truck_Plate_Number")["Timestamp"].apply(lambda s: sorted(s.dropna().tolist())).to_dict()

    # Product group: prefer status of the date, then fallback to logistic_for_date, then full history
    prod_from_status = status_for_date.groupby("Truck_Plate_Number")["Product_Group"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else np.nan)
    prod_from_log_date = logistic_for_date.groupby("Truck_Plate_Number")["Product_Group"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else np.nan)
    # fallback to any status/product in historical df_status if still missing
    prod_from_status_hist = df_status.groupby("Truck_Plate_Number")["Product_Group"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else np.nan)

    product = prod_from_status.combine_first(prod_from_log_date).combine_first(prod_from_status_hist).rename("Product_Group")

    # Build base set of truck plates (union across relevant dfs)
    trucks = pd.Index(sorted(
        set(df_status["Truck_Plate_Number"].dropna().unique())
        | set(df_logistic["Truck_Plate_Number"].dropna().unique())
        | set(df_security["Truck_Plate_Number"].dropna().unique())
        | set(df_driver["Truck_Plate_Number"].dropna().unique())
    ), name="Truck_Plate_Number")

    kpi = pd.DataFrame(index=trucks)
    kpi = kpi.join(arrival).join(start_loading).join(product)

    # Join some helpers for transparency (first security ts on that date, last logistic ts on that date)
    if not security_for_date.empty:
        first_sec = security_for_date.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("First_Security_Timestamp")
        kpi = kpi.join(first_sec)
    else:
        kpi = kpi.join(df_security.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("First_Security_Timestamp"))

    if not logistic_for_date.empty:
        logistic_last = logistic_for_date.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_max).rename("Logistic_Last_Timestamp")
        kpi = kpi.join(logistic_last)
    else:
        kpi = kpi.join(df_logistic.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_max).rename("Logistic_Last_Timestamp"))

    # --- Determine Completed_Time with date-aware logic ---
    end_times = {}
    for truck in kpi.index:
        start_ts = kpi.at[truck, "Start_Loading_Time"] if "Start_Loading_Time" in kpi.columns else pd.NaT
        chosen_end = pd.NaT

        comp_list = completed_grouped.get(truck, [])
        if len(comp_list) > 0:
            if pd.notna(start_ts):
                ge = [t for t in comp_list if t >= start_ts]
                if ge:
                    chosen_end = ge[0]
                else:
                    chosen_end = comp_list[-1]
            else:
                chosen_end = comp_list[0]

        # fallback to logistic_last_ts on the date if allowed
        if pd.isna(chosen_end) and use_fallbacks:
            if pd.notna(kpi.at[truck, "Logistic_Last_Timestamp"]):
                chosen_end = kpi.at[truck, "Logistic_Last_Timestamp"]

        end_times[truck] = chosen_end

    kpi["Completed_Time"] = pd.Series(end_times, name="Completed_Time")

    # --- Durations (minutes) ---
    def td_min(start, end):
        if pd.isna(start) or pd.isna(end):
            return np.nan
        return (end - start) / pd.Timedelta(minutes=1)

    kpi["Waiting_min"] = kpi.apply(lambda r: td_min(r.get("Arrival_Time"), r.get("Start_Loading_Time")), axis=1)
    kpi["Loading_min"] = kpi.apply(lambda r: td_min(r.get("Start_Loading_Time"), r.get("Completed_Time")), axis=1)
    kpi["Total_min"]   = kpi.apply(lambda r: td_min(r.get("Arrival_Time"), r.get("Completed_Time")), axis=1)

    # --- Date attribution: prefer Arrival_Time.date, else Start_Loading_Time.date, else Completed_Time.date
    def derive_date(row):
        for c in ["Arrival_Time", "Start_Loading_Time", "Completed_Time"]:
            v = row.get(c)
            if pd.notna(v):
                try:
                    # handle tz-aware
                    if hasattr(v, "tz"):
                        return pd.to_datetime(v).tz_convert(LOCAL_TZ).date()
                    else:
                        return pd.to_datetime(v).date()
                except Exception:
                    try:
                        return pd.to_datetime(v).date()
                    except Exception:
                        continue
        return pd.NaT

    kpi["Date"] = kpi.apply(derive_date, axis=1)

    # Data quality flag
    def quality_flag(row):
        missing = []
        if pd.isna(row.get("Arrival_Time")):
            missing.append("Missing_Arrival")
        if pd.isna(row.get("Start_Loading_Time")):
            missing.append("Missing_Start")
        if pd.isna(row.get("Completed_Time")):
            missing.append("Missing_Completed")
        return ";".join(missing) if missing else "OK"

    kpi["Data_Quality_Flag"] = kpi.apply(quality_flag, axis=1)

    kpi = kpi.reset_index()

    # Apply filters:
    #  - selected_date: keep only rows with Date == selected_date (if provided)
    if selected_date is not None:
        kpi = kpi[pd.to_datetime(kpi["Date"]).dt.date == selected_date]

    # product filter
    if product_filter:
        kpi = kpi[kpi["Product_Group"].isin(product_filter)]

    # upload_type (from security first-known)
    if upload_type:
        if "Coming_to_Upload_or_Unload" in df_security.columns:
            sec_map = df_security.groupby("Truck_Plate_Number")["Coming_to_Upload_or_Unload"].agg("first")
            kpi = kpi.join(sec_map, on="Truck_Plate_Number")
            kpi = kpi[kpi["Coming_to_Upload_or_Unload"] == upload_type]

    # Select columns and order for display
    display_cols = [
        "Truck_Plate_Number", "Product_Group", "Date",
        "Arrival_Time", "Start_Loading_Time", "Completed_Time",
        "Waiting_min", "Loading_min", "Total_min",
        "Data_Quality_Flag"
    ]
    existing_cols = [c for c in display_cols if c in kpi.columns]
    return kpi[existing_cols].sort_values(["Product_Group", "Date", "Truck_Plate_Number"])
