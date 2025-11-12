# data/metrics.py (final version for now)
import pandas as pd
import numpy as np

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
    # ensure timestamps
    for df in [df_security, df_status, df_logistic, df_driver]:
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

    # ---- Status events only ----
    arrival = df_status[df_status["Status"] == "Arrival"].groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("Arrival_Time")
    start_loading = df_status[df_status["Status"] == "Start_Loading"].groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("Start_Loading_Time")
    completed_all = df_status[df_status["Status"] == "Completed"].copy()

    prod_from_status = df_status.groupby("Truck_Plate_Number")["Product_Group"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else np.nan)
    prod_from_log = df_logistic.groupby("Truck_Plate_Number")["Product_Group"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else np.nan)
    product = prod_from_status.combine_first(prod_from_log).rename("Product_Group")

    trucks = pd.Index(sorted(
        set(df_status["Truck_Plate_Number"].dropna().unique())
        | set(df_logistic["Truck_Plate_Number"].dropna().unique())
        | set(df_security["Truck_Plate_Number"].dropna().unique())
        | set(df_driver["Truck_Plate_Number"].dropna().unique())
    ), name="Truck_Plate_Number")

    kpi = pd.DataFrame(index=trucks)
    kpi = kpi.join(arrival).join(start_loading).join(product)

    # Completed logic
    completed_grouped = completed_all.groupby("Truck_Plate_Number")["Timestamp"].apply(list).to_dict()
    end_times = {}
    for truck in kpi.index:
        start_ts = kpi.at[truck, "Start_Loading_Time"] if "Start_Loading_Time" in kpi.columns else pd.NaT
        comp_list = completed_grouped.get(truck, [])
        chosen = pd.NaT
        if comp_list:
            if pd.notna(start_ts):
                later = [t for t in comp_list if t >= start_ts]
                chosen = later[0] if later else comp_list[-1]
            else:
                chosen = comp_list[0]
        end_times[truck] = chosen
    kpi["Completed_Time"] = pd.Series(end_times)

    # Durations
    def td_min(a, b):
        if pd.isna(a) or pd.isna(b):
            return np.nan
        return (b - a) / pd.Timedelta(minutes=1)

    kpi["Waiting_min"] = kpi.apply(lambda r: td_min(r["Arrival_Time"], r["Start_Loading_Time"]), axis=1)
    kpi["Loading_min"] = kpi.apply(lambda r: td_min(r["Start_Loading_Time"], r["Completed_Time"]), axis=1)
    kpi["Total_min"] = kpi.apply(lambda r: td_min(r["Arrival_Time"], r["Completed_Time"]), axis=1)

    kpi["Date"] = pd.to_datetime(kpi["Arrival_Time"]).dt.date

    # Quality flag
    def flag(r):
        missing = []
        if pd.isna(r["Arrival_Time"]): missing.append("Missing_Arrival")
        if pd.isna(r["Start_Loading_Time"]): missing.append("Missing_Start")
        if pd.isna(r["Completed_Time"]): missing.append("Missing_Completed")
        return ";".join(missing) if missing else "OK"
    kpi["Data_Quality_Flag"] = kpi.apply(flag, axis=1)

    kpi = kpi.reset_index()

    # Apply filters
    if selected_date is not None:
        kpi = kpi[kpi["Date"] == selected_date]
    if product_filter:
        kpi = kpi[kpi["Product_Group"].isin(product_filter)]
    if upload_type:
        if "Coming_to_Upload_or_Unload" in df_security.columns:
            sec_map = df_security[["Truck_Plate_Number", "Coming_to_Upload_or_Unload"]].drop_duplicates("Truck_Plate_Number").set_index("Truck_Plate_Number")
            kpi = kpi.join(sec_map, on="Truck_Plate_Number")
            kpi = kpi[kpi["Coming_to_Upload_or_Unload"] == upload_type]

    cols = [
        "Truck_Plate_Number", "Product_Group", "Date",
        "Arrival_Time", "Start_Loading_Time", "Completed_Time",
        "Waiting_min", "Loading_min", "Total_min",
        "Data_Quality_Flag"
    ]
    return kpi[cols].sort_values(["Product_Group", "Date", "Truck_Plate_Number"])
