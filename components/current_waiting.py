# components/current_waiting.py
import streamlit as st
import pandas as pd
from config.config import LOCAL_TZ


def show_current_waiting(df_security, df_status, df_driver, df_logistic=None, product_filter=None, upload_type=None, truck_condition=None, selected_date=None, start_date=None, end_date=None):
    """
    Show trucks currently waiting.
    A truck is considered waiting if:
        - On the SELECTED DATE or within DATE RANGE
        - Its LATEST status for that date = "Arrival"
        - No later "Start_Loading" or "Completed" record on that date
    Includes automatic cleanup of previous-day visits (same plate number).
    """

    # --- Standardize Timestamps ---
    for df in (df_security, df_status, df_driver):
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

    # --- Timezone-aware "now" ---
    try:
        now = pd.Timestamp.now(tz=LOCAL_TZ)
    except Exception:
        now = pd.Timestamp.now()

    # --- Filter status by date or date range ---
    df_status["Date"] = df_status["Timestamp"].dt.date
    
    if selected_date:
        # Single date filter
        status_filtered = df_status[df_status["Date"] == selected_date]
    elif start_date or end_date:
        # Date range filter
        if start_date and end_date:
            status_filtered = df_status[(df_status["Date"] >= start_date) & (df_status["Date"] <= end_date)]
        elif start_date:
            status_filtered = df_status[df_status["Date"] >= start_date]
        elif end_date:
            status_filtered = df_status[df_status["Date"] <= end_date]
    else:
        # No date filter - use today
        today = now.date()
        status_filtered = df_status[df_status["Date"] == today]

    if status_filtered.empty:
        st.subheader("Current Waiting Trucks")
        st.info("No truck activity recorded for the selected date range.")
        return

    # --- CLEANUP: Get latest status per truck+product within the filtered date range ---
    if "Product_Group" in status_filtered.columns:
        latest_today = (
            status_filtered.sort_values("Timestamp")
            .groupby(["Truck_Plate_Number", "Product_Group"])
            .last()
            .reset_index()
        )
    else:
        latest_today = (
            status_filtered.sort_values("Timestamp")
            .groupby("Truck_Plate_Number")
            .last()
            .reset_index()
        )

    # Keep only those whose FINAL status today is "Arrival" (== still waiting)
    waiting = latest_today[latest_today["Status"] == "Arrival"].copy()

    if waiting.empty:
        st.subheader("Current Waiting Trucks")
        st.info("No current waiting trucks for the selected filters.")
        return

    # Rename timestamp for clarity
    waiting = waiting.rename(columns={"Timestamp": "Arrival_Time"})

    # --- Merge Coming_to_Upload_or_Unload from Security ---
    if "Coming_to_Load_or_Unload" in df_security.columns:
        sec_map = (
            df_security.sort_values("Timestamp")
            .groupby("Truck_Plate_Number")["Coming_to_Load_or_Unload"]
            .last()
            .reset_index()
        )
        waiting = waiting.merge(sec_map, on="Truck_Plate_Number", how="left")

    # --- Merge Driver Info (latest record per truck) ---
    if "Truck_Plate_Number" in df_driver.columns:
        drv = (
            df_driver.sort_values("Timestamp")
            .groupby("Truck_Plate_Number")
            .last()[["Driver_Name", "Phone_Number"]]
            .reset_index()
        )
        waiting = waiting.merge(drv, on="Truck_Plate_Number", how="left")

    # --- Add Date column for merging ---
    if "Date" not in waiting.columns:
        waiting["Date"] = pd.to_datetime(waiting["Arrival_Time"], errors="coerce").dt.date

    # --- Merge Total_Weight_MT from logistic (per Truck + Product + Date) if provided ---
    if df_logistic is not None and "Total_Weight_MT" in df_logistic.columns:
        lf = df_logistic.copy()
        if "Timestamp" in lf.columns:
            lf["Timestamp"] = pd.to_datetime(lf["Timestamp"], errors="coerce")
            lf["_Date"] = lf["Timestamp"].dt.date
        else:
            lf["_Date"] = None

        if "Product_Group" in lf.columns and "Product_Group" in waiting.columns:
            weight_map = (
                lf.groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Total_Weight_MT"]
                .sum()
                .reset_index()
                .rename(columns={"_Date": "Date"})
            )
            
            waiting = waiting.merge(
                weight_map,
                on=["Truck_Plate_Number", "Product_Group", "Date"],
                how="left"
            )
            
        # ensure column exists
        if "Total_Weight_MT" not in waiting.columns:
            waiting["Total_Weight_MT"] = None
    
    # --- Merge Truck_Condition from logistic (per Truck + Product + Date) ---
    if df_logistic is not None and "Truck_Condition" in df_logistic.columns:
        lf_cond = df_logistic.copy()
        if "Timestamp" in lf_cond.columns:
            lf_cond["Timestamp"] = pd.to_datetime(lf_cond["Timestamp"], errors="coerce")
            lf_cond["_Date"] = lf_cond["Timestamp"].dt.date
        else:
            lf_cond["_Date"] = None

        if "Product_Group" in lf_cond.columns and "Product_Group" in waiting.columns:
            condition_map = (
                lf_cond.groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Truck_Condition"]
                .first()
                .reset_index()
                .rename(columns={"_Date": "Date"})
            )
            
            waiting = waiting.merge(
                condition_map,
                on=["Truck_Plate_Number", "Product_Group", "Date"],
                how="left"
            )
        
        if "Truck_Condition" not in waiting.columns:
            waiting["Truck_Condition"] = None

    # --- Apply Filters ---
    if product_filter:
        waiting = waiting[waiting["Product_Group"].isin(product_filter)]

    if upload_type and "Coming_to_Load_or_Unload" in waiting.columns:
        waiting = waiting[waiting["Coming_to_Load_or_Unload"] == upload_type]
    
    if truck_condition and "Truck_Condition" in waiting.columns:
        waiting = waiting[waiting["Truck_Condition"] == truck_condition]

    # --- Compute correct Waiting time ---
    waiting["Waiting_min"] = (now - waiting["Arrival_Time"]) / pd.Timedelta(minutes=1)

    # Rename for display
    if "Coming_to_Load_or_Unload" in waiting.columns:
        waiting = waiting.rename(columns={"Coming_to_Load_or_Unload": "Coming_to_load_or_Unload"})

    # --- Add Outbound_Delivery_No from logistic sheet ---
    if df_logistic is not None and not df_logistic.empty:
        if "Outbound_Delivery_No" in df_logistic.columns and "Truck_Plate_Number" in df_logistic.columns:
            # Ensure _Date exists in logistic
            if "_Date" not in df_logistic.columns:
                if "Timestamp" in df_logistic.columns:
                    df_logistic["Timestamp"] = pd.to_datetime(df_logistic["Timestamp"], errors="coerce")
                    df_logistic["_Date"] = df_logistic["Timestamp"].dt.date
                else:
                    df_logistic["_Date"] = None
            
            # Build delivery map per Truck + Product + Date
            if "Product_Group" in df_logistic.columns and "Product_Group" in waiting.columns:
                delivery_map = (
                    df_logistic
                    .groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Outbound_Delivery_No"]
                    .agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else None)
                    .reset_index()
                    .rename(columns={"_Date": "Date"})
                )
                
                # Merge with waiting trucks
                if "Date" in waiting.columns:
                    waiting = waiting.merge(
                        delivery_map,
                        on=["Truck_Plate_Number", "Product_Group", "Date"],
                        how="left"
                    )
            
            if "Outbound_Delivery_No" not in waiting.columns:
                waiting["Outbound_Delivery_No"] = None

    # Round numeric columns to 2 decimal places
    for col in ["Total_Weight_MT", "Waiting_min"]:
        if col in waiting.columns:
            waiting[col] = pd.to_numeric(waiting[col], errors="coerce").round(2)

    display_cols = [
        "Date",
        "Product_Group",
        "Coming_to_load_or_Unload",
        "Truck_Condition",
        "Truck_Plate_Number",
        "Outbound_Delivery_No",
        "Total_Weight_MT",
        "Arrival_Time",
        "Waiting_min",
        "Phone_Number",
        "Driver_Name",
    ]

    # Final safety: only show columns that exist
    display_cols = [c for c in display_cols if c in waiting.columns]

    # # --- Display ---
    # st.subheader("Current Waiting Trucks")
    # st.dataframe(
    #     waiting[display_cols]
    #     .sort_values("Waiting_min", ascending=False)
    #     .reset_index(drop=True),
    #     hide_index=True
    # )

    # --- Format time-only display ---
    time_cols = ["Arrival_Time"]
    for c in time_cols:
        if c in waiting.columns:
            waiting[c] = waiting[c].dt.strftime("%H:%M:%S")

    # --- Display ---
    st.subheader("Current Waiting Trucks")
    df_view = waiting[display_cols].sort_values("Waiting_min", ascending=False).reset_index(drop=True)
    st.dataframe(df_view, hide_index=True, use_container_width=True)


