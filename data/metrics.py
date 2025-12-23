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
    start_date=None,
    end_date=None,
    product_filter=None,
    upload_type=None,
    use_fallbacks=False
):
    """
    Compute per-truck arrival/start/completed and durations.
    If selected_date is provided (a date object), only events on that date are used.
    If start_date and end_date are provided, events within that range (inclusive) are used.
    This avoids old historical rows interfering with metrics.
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

    # Filter by date or date range
    def _filter_by_date(df, single_date=None, start=None, end=None):
        if single_date is None and start is None and end is None:
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
        
        # Apply filter based on what's provided
        if single_date is not None:
            return df[dates == single_date].copy()
        elif start is not None and end is not None:
            return df[(dates >= start) & (dates <= end)].copy()
        elif start is not None:
            return df[dates >= start].copy()
        elif end is not None:
            return df[dates <= end].copy()
        return df.copy()

    status_for_date = _filter_by_date(df_status, selected_date, start_date, end_date)
    logistic_for_date = _filter_by_date(df_logistic, selected_date, start_date, end_date)
    security_for_date = _filter_by_date(df_security, selected_date, start_date, end_date)
    driver_for_date = _filter_by_date(df_driver, selected_date, start_date, end_date)

    # ---- Compute primary events using rows FROM THE SELECTED DATE only ----
    # Arrival: For multi-product visits, get arrival per TRUCK+PRODUCT (not just per truck)
    # This allows each product group to have its own arrival timestamp
    arrival_all = status_for_date[status_for_date["Status"] == "Arrival"].copy()
    if not arrival_all.empty and {"Truck_Plate_Number", "Product_Group"}.issubset(arrival_all.columns):
        # Group by Truck + Product to get earliest arrival per product
        arrival_prod = (
            arrival_all.groupby(["Truck_Plate_Number", "Product_Group"])["Timestamp"]
            .agg(_safe_min)
            .rename("Arrival_Time")
            .reset_index()
        )
    elif not status_for_date.empty and "Truck_Plate_Number" in status_for_date.columns:
        # Fallback: arrival per truck only if no product info or missing Product_Group
        arrival_prod = (
            status_for_date[status_for_date["Status"] == "Arrival"]
            .groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min)
            .rename("Arrival_Time").reset_index()
        )
        if not arrival_prod.empty:
            arrival_prod["Product_Group"] = None
    else:
        arrival_prod = pd.DataFrame(columns=["Truck_Plate_Number", "Product_Group", "Arrival_Time"]) 

    # Start loading: earliest Start_Loading event on that date PER TRUCK+PRODUCT
    start_loading_prod = status_for_date[status_for_date["Status"] == "Start_Loading"].copy()
    if not start_loading_prod.empty and {"Truck_Plate_Number", "Product_Group"}.issubset(start_loading_prod.columns):
        start_loading_prod = (
            start_loading_prod.groupby(["Truck_Plate_Number", "Product_Group"])["Timestamp"]
            .agg(_safe_min)
            .rename("Start_Loading_Time")
            .reset_index()
        )
    else:
        start_loading_prod = pd.DataFrame(columns=["Truck_Plate_Number", "Product_Group", "Start_Loading_Time"]) 

    # Completed events on that date (keep list) PER TRUCK+PRODUCT
    completed_all = status_for_date[status_for_date["Status"] == "Completed"].copy()
    if not completed_all.empty and {"Truck_Plate_Number", "Product_Group"}.issubset(completed_all.columns):
        completed_grouped = (
            completed_all.groupby(["Truck_Plate_Number", "Product_Group"])["Timestamp"]
            .apply(lambda s: sorted(s.dropna().tolist()))
            .to_dict()
        )
    else:
        # fallback to empty dict
        completed_grouped = {}

    # --- Product groups per truck (support multi-product visits) ---
    # Gather all product groups observed per truck across status/logistic (date-limited) and historical status
    from collections import defaultdict

    prod_sets = defaultdict(set)
    def _accumulate_products(df):
        if "Product_Group" not in df.columns or "Truck_Plate_Number" not in df.columns:
            return
        for truck, grp in df.groupby("Truck_Plate_Number")["Product_Group"]:
            vals = [v for v in pd.Series(grp).dropna().unique().tolist() if pd.notna(v)]
            for v in vals:
                prod_sets[truck].add(v)

    _accumulate_products(status_for_date)
    _accumulate_products(logistic_for_date)
    _accumulate_products(df_status)

    # Build base set of truck plates (union across relevant dfs)
    trucks = sorted(
        set(df_status.get("Truck_Plate_Number", pd.Series(dtype=object)).dropna().unique())
        | set(df_logistic.get("Truck_Plate_Number", pd.Series(dtype=object)).dropna().unique())
        | set(df_security.get("Truck_Plate_Number", pd.Series(dtype=object)).dropna().unique())
        | set(df_driver.get("Truck_Plate_Number", pd.Series(dtype=object)).dropna().unique())
    )

    # Expand to one row per (Truck_Plate_Number, Product_Group). If no product groups found for a truck,
    # still include a row with Product_Group = NaN so that truck-level metrics are visible.
    rows = []
    for truck in trucks:
        pset = sorted(prod_sets.get(truck, []))
        if pset:
            for pg in pset:
                rows.append({"Truck_Plate_Number": truck, "Product_Group": pg})
        else:
            rows.append({"Truck_Plate_Number": truck, "Product_Group": np.nan})

    kpi = pd.DataFrame(rows)

    # Join product-specific Arrival onto kpi by Truck_Plate_Number + Product_Group
    if not arrival_prod.empty:
        kpi = kpi.merge(arrival_prod, on=["Truck_Plate_Number", "Product_Group"], how="left")
    else:
        kpi["Arrival_Time"] = pd.NaT

    # Join product-specific Start_Loading onto kpi by Truck_Plate_Number + Product_Group
    if not start_loading_prod.empty:
        kpi = kpi.merge(start_loading_prod, on=["Truck_Plate_Number", "Product_Group"], how="left")
    else:
        kpi = kpi.merge(pd.DataFrame(columns=["Truck_Plate_Number", "Product_Group", "Start_Loading_Time"]), on=["Truck_Plate_Number", "Product_Group"], how="left")

    # For transparency, also keep a product-from-status hint (first seen) per truck if needed elsewhere
    # but we keep kpi rows per product group for display/weight merging.

    # Join some helpers for transparency (first security ts on that date, last logistic ts on that date)
    if not security_for_date.empty:
        first_sec = security_for_date.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("First_Security_Timestamp").reset_index()
    else:
        first_sec = df_security.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_min).rename("First_Security_Timestamp").reset_index()
    kpi = kpi.merge(first_sec, on="Truck_Plate_Number", how="left")

    if not logistic_for_date.empty:
        logistic_last = logistic_for_date.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_max).rename("Logistic_Last_Timestamp").reset_index()
    else:
        logistic_last = df_logistic.groupby("Truck_Plate_Number")["Timestamp"].agg(_safe_max).rename("Logistic_Last_Timestamp").reset_index()
    kpi = kpi.merge(logistic_last, on="Truck_Plate_Number", how="left")

    # --- Determine Completed_Time with date-aware logic per (truck, product) row ---
    # Build a map of start times per (truck, product)
    start_map = {}
    if not start_loading_prod.empty:
        for _, r in start_loading_prod.iterrows():
            start_map[(r["Truck_Plate_Number"], r["Product_Group"])] = r["Start_Loading_Time"]

    end_times = []
    for _, row in kpi.iterrows():
        truck = row.get("Truck_Plate_Number")
        prod = row.get("Product_Group")
        chosen_end = pd.NaT

        comp_list = completed_grouped.get((truck, prod), [])
        start_ts = start_map.get((truck, prod), pd.NaT)

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
            ll = logistic_last[logistic_last["Truck_Plate_Number"] == truck]["Logistic_Last_Timestamp"]
            if not ll.empty and pd.notna(ll.iloc[0]):
                chosen_end = ll.iloc[0]

        end_times.append({"Truck_Plate_Number": truck, "Product_Group": prod, "Completed_Time": chosen_end})

    completed_df = pd.DataFrame(end_times)
    if not completed_df.empty:
        kpi = kpi.merge(completed_df, on=["Truck_Plate_Number", "Product_Group"], how="left")
    else:
        kpi["Completed_Time"] = pd.NaT

    # --- DURATION CALCULATIONS (your rules) ---

    def td_min(start, end):
        if pd.isna(start) or pd.isna(end):
            return None
        return (end - start) / pd.Timedelta(minutes=1)

    # Validation: Check if timestamps are in correct order
    # Correct order: Arrival < Start_Loading < Completed
    def validate_order(row):
        """
        Returns tuple: (is_valid, error_type)
        is_valid: True if order is correct, False otherwise
        error_type: Description of the error if invalid
        """
        arrival = row.get("Arrival_Time")
        start = row.get("Start_Loading_Time")
        completed = row.get("Completed_Time")
        
        # If all are missing, no validation error
        if pd.isna(arrival) and pd.isna(start) and pd.isna(completed):
            return True, None
        
        # Check all possible wrong orders
        if pd.notna(completed) and pd.notna(start):
            if completed < start:
                return False, "Completed before Start Loading"
        
        if pd.notna(completed) and pd.notna(arrival):
            if completed < arrival:
                return False, "Completed before Arrival"
        
        if pd.notna(start) and pd.notna(arrival):
            if start < arrival:
                return False, "Start Loading before Arrival"
        
        return True, None

    # Apply validation
    validation_results = kpi.apply(validate_order, axis=1, result_type='expand')
    kpi["Is_Valid_Order"] = validation_results[0]
    kpi["Order_Error"] = validation_results[1]

    # 1) Waiting_min = ABS(time difference)
    kpi["Waiting_min"] = kpi.apply(
        lambda r: abs(td_min(r.get("Arrival_Time"), r.get("Start_Loading_Time")))
        if td_min(r.get("Arrival_Time"), r.get("Start_Loading_Time")) is not None
        else None,
        axis=1
    )

    # 2) Loading_min = ABS(time difference)
    kpi["Loading_min"] = kpi.apply(
        lambda r: abs(td_min(r.get("Start_Loading_Time"), r.get("Completed_Time")))
        if td_min(r.get("Start_Loading_Time"), r.get("Completed_Time")) is not None
        else None,
        axis=1
    )

    # 3) Total_min rules:
    #    - Both exist → waiting + loading
    #    - Only loading exists → loading
    #    - Only waiting exists → None
    #    - None → None
    def compute_total(row):
        w = row.get("Waiting_min")
        l = row.get("Loading_min")

        if w is not None and l is not None:
            return w + l
        if w is None and l is not None:
            return l
        if w is not None and l is None:
            return None
        return None

    kpi["Total_min"] = kpi.apply(compute_total, axis=1)



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
    # normalize column names (strip accidental whitespace/newlines)
    try:
        kpi.columns = kpi.columns.str.strip()
    except Exception:
        kpi.columns = [c.strip() if isinstance(c, str) else c for c in kpi.columns]
    # Normalize any internal whitespace/newlines within column names to single spaces
    try:
        import re
        kpi.columns = [re.sub(r"\s+", " ", c).strip() if isinstance(c, str) else c for c in kpi.columns]
    except Exception:
        pass

    # Apply filters:
    #  - Filter by date: single date or date range (if provided)
    import datetime as _dt

    def _to_date_scalar(x):
        if x is None:
            return None
        if isinstance(x, pd.Timestamp):
            try:
                if x.tz is not None:
                    x = x.tz_convert(LOCAL_TZ)
            except Exception:
                pass
            return x.date()
        if isinstance(x, _dt.datetime):
            return x.date()
        if isinstance(x, _dt.date):
            return x
        try:
            y = pd.to_datetime(x, errors="coerce")
            if pd.isna(y):
                return None
            return y.date()
        except Exception:
            return None

    if selected_date is not None:
        sel_date = _to_date_scalar(selected_date)
        kpi_dates_dt = pd.to_datetime(kpi["Date"], errors="coerce").dt.normalize()
        sel_ts = pd.Timestamp(sel_date) if sel_date is not None else None
        if sel_ts is not None:
            kpi = kpi[kpi_dates_dt == sel_ts]
    elif start_date is not None or end_date is not None:
        s_date = _to_date_scalar(start_date)
        e_date = _to_date_scalar(end_date)
        kpi_dates_dt = pd.to_datetime(kpi["Date"], errors="coerce").dt.normalize()
        s_ts = pd.Timestamp(s_date) if s_date is not None else None
        e_ts = pd.Timestamp(e_date) if e_date is not None else None
        if s_ts is not None and e_ts is not None:
            kpi = kpi[(kpi_dates_dt >= s_ts) & (kpi_dates_dt <= e_ts)]
        elif s_ts is not None:
            kpi = kpi[kpi_dates_dt >= s_ts]
        elif e_ts is not None:
            kpi = kpi[kpi_dates_dt <= e_ts]

    # product filter
    if product_filter:
        kpi = kpi[kpi["Product_Group"].isin(product_filter)]

    # upload_type (from security first-known)
    if upload_type:
        if "Coming_to_Load_or_Unload" in df_security.columns:
            # Prefer security records from the selected date (if provided) so we filter by
            # the action that occurred on that date for the truck (Loading vs Unloading).
            if (selected_date is not None or start_date is not None or end_date is not None) and not security_for_date.empty:
                sec = security_for_date.copy()
                if "Timestamp" in sec.columns:
                    sec["_Date"] = pd.to_datetime(sec["Timestamp"], errors="coerce").dt.date
                else:
                    sec["_Date"] = None
                sec_map = sec.groupby(["Truck_Plate_Number", "_Date"])["Coming_to_Load_or_Unload"].agg("first").reset_index().rename(columns={"_Date": "Date"})
                # Merge on Truck + Date for accurate per-day filtering
                kpi = kpi.merge(sec_map, on=["Truck_Plate_Number", "Date"], how="left")
            else:
                # Fallback: use first-known security state per truck (historic)
                sec_map = df_security.groupby("Truck_Plate_Number")["Coming_to_Load_or_Unload"].agg("first").reset_index()
                kpi = kpi.merge(sec_map, on="Truck_Plate_Number", how="left")

            kpi = kpi[kpi["Coming_to_Load_or_Unload"] == upload_type]

    # Select columns and order for display
    display_cols = [
        "Truck_Plate_Number", "Product_Group", "Date",
        "Arrival_Time", "Start_Loading_Time", "Completed_Time",
        "Waiting_min", "Loading_min", "Total_min",
        "Data_Quality_Flag", "Is_Valid_Order", "Order_Error"
    ]
    existing_cols = [c for c in display_cols if c in kpi.columns]
    return kpi[existing_cols].sort_values(["Product_Group", "Date", "Truck_Plate_Number"])
