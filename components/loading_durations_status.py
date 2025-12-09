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


def show_loading_durations_status(dfs, selected_date=None, start_date=None, end_date=None, product_selected=None, upload_type=None, truck_condition=None):
    """
    Display Loading Durations Status with Total_Weight_MT, Loading_Rate and Mission.
    Total_Weight_MT is aggregated per (Truck_Plate_Number, Product_Group, Date)
    to avoid summing weights across product groups or dates.
    Supports both single date and date range filtering.
    """
    df_security = dfs['security']
    df_status = dfs['status']
    df_logistic = dfs['logistic']
    df_driver = dfs['driver']

    # Compute core per-truck metrics (strict mode)
    df_kpi = compute_per_truck_metrics(
        df_security, df_status, df_logistic, df_driver,
        selected_date=selected_date,
        start_date=start_date,
        end_date=end_date,
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

    # --- Add Outbound_Delivery_No from logistic sheet ---
    delivery_map = None
    if "Outbound_Delivery_No" in df_logistic.columns and "Truck_Plate_Number" in df_logistic.columns:
        # Ensure _Date exists (was created above when building weight_map)
        if "_Date" not in df_logistic.columns:
            if "Timestamp" in df_logistic.columns:
                df_logistic["Timestamp"] = pd.to_datetime(df_logistic["Timestamp"], errors="coerce")
                df_logistic["_Date"] = df_logistic["Timestamp"].dt.date
            else:
                df_logistic["_Date"] = None
        
        # Build delivery map per Truck + Product + Date (take first non-null if multiple)
        if "Product_Group" in df_logistic.columns:
            delivery_map = (
                df_logistic
                .groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Outbound_Delivery_No"]
                .agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else None)
                .reset_index()
                .rename(columns={"_Date": "Date"})
            )
            # Convert Date to proper type
            if delivery_map["Date"].isnull().any():
                delivery_map["Date"] = delivery_map["Date"].where(~delivery_map["Date"].isnull(), None)
    
    if delivery_map is not None:
        if "Date" not in df_kpi.columns:
            df_kpi["Date"] = None
        df_kpi = df_kpi.merge(
            delivery_map,
            on=["Truck_Plate_Number", "Product_Group", "Date"],
            how="left"
        )
    else:
        df_kpi["Outbound_Delivery_No"] = None

    # --- Add Phone_Number (prefer driver table, fallback to security) ---
    phone_map = None
    if "Phone_Number" in df_driver.columns and "Truck_Plate_Number" in df_driver.columns:
        phone_map = df_driver.groupby("Truck_Plate_Number")["Phone_Number"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else None).reset_index()
    elif "Phone_Number" in df_security.columns and "Truck_Plate_Number" in df_security.columns:
        phone_map = df_security.groupby("Truck_Plate_Number")["Phone_Number"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else None).reset_index()

    if phone_map is not None:
        df_kpi = df_kpi.merge(phone_map, on="Truck_Plate_Number", how="left")
    else:
        df_kpi["Phone_Number"] = None

    # --- Add Truck_Condition from logistic table ---
    if "Truck_Condition" in df_logistic.columns and "Truck_Plate_Number" in df_logistic.columns:
        # Ensure _Date exists
        if "_Date" not in df_logistic.columns:
            if "Timestamp" in df_logistic.columns:
                df_logistic["Timestamp"] = pd.to_datetime(df_logistic["Timestamp"], errors="coerce")
                df_logistic["_Date"] = df_logistic["Timestamp"].dt.date
            else:
                df_logistic["_Date"] = None
        
        if "Product_Group" in df_logistic.columns:
            condition_map = (
                df_logistic
                .groupby(["Truck_Plate_Number", "Product_Group", "_Date"], dropna=False)["Truck_Condition"]
                .first()
                .reset_index()
                .rename(columns={"_Date": "Date"})
            )
            
            if "Date" not in df_kpi.columns:
                df_kpi["Date"] = None
            
            df_kpi = df_kpi.merge(
                condition_map,
                on=["Truck_Plate_Number", "Product_Group", "Date"],
                how="left"
            )
    
    if "Truck_Condition" not in df_kpi.columns:
        df_kpi["Truck_Condition"] = None

    # --- Add Coming_to_Load_or_Unload from security table ---
    if "Coming_to_Load_or_Unload" in df_security.columns and "Truck_Plate_Number" in df_security.columns:
        coming_map = (
            df_security.sort_values("Timestamp")
            .groupby("Truck_Plate_Number")["Coming_to_Load_or_Unload"]
            .last()
            .reset_index()
        )
        df_kpi = df_kpi.merge(coming_map, on="Truck_Plate_Number", how="left")
    else:
        df_kpi["Coming_to_Load_or_Unload"] = None

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

    # Rename Loading_Rate to Loading_Rate_min/MT for clarity, and add Loading_Rate_MT/Hour
    if "Loading_Rate" in df_kpi.columns:
        df_kpi = df_kpi.rename(columns={"Loading_Rate": "Loading_Rate_min/MT"})

    def compute_mt_per_hour(r):
        try:
            wt = r.get("Total_Weight_MT")
            lm = r.get("Loading_min")
            if pd.isna(wt) or pd.isna(lm) or lm == 0:
                return None
            return (float(wt) * 60.0) / float(lm)
        except Exception:
            return None

    df_kpi["Loading_Rate_MT/Hour"] = df_kpi.apply(compute_mt_per_hour, axis=1)
    # Nicely round numeric rates to 2 decimal places
    for col in ["Loading_Rate_min/MT", "Loading_Rate_MT/Hour", "Waiting_min", "Loading_min", "Total_Weight_MT"]:
        if col in df_kpi.columns:
            df_kpi[col] = pd.to_numeric(df_kpi[col], errors="coerce").round(2)

    # Add Mission column
    df_kpi["Mission"] = df_kpi.apply(_compute_mission, axis=1)

    # Reorder columns for display (adjust as you prefer)
    display_cols = [
        "Date",
        "Product_Group",
        "Coming_to_Load_or_Unload",
        "Truck_Condition",
        "Truck_Plate_Number",
        "Arrival_Time",
        "Start_Loading_Time",
        "Completed_Time",
        "Waiting_min",
        "Loading_min",
        "Total_Weight_MT",
        "Loading_Rate_min/MT",
        "Loading_Rate_MT/Hour",
        "Outbound_Delivery_No",
        "Phone_Number",
        "Mission",
        "Is_Valid_Order",
        "Order_Error"
    ]
    display_cols = [c for c in display_cols if c in df_kpi.columns]

    # --- Format timestamp columns to show ONLY time (if datetime) ---
    # IMPORTANT: Do this AFTER rounding numeric columns
    time_cols = ["Arrival_Time", "Start_Loading_Time", "Completed_Time"]
    for c in time_cols:
        if c in df_kpi.columns:
            # convert tz-aware datetimes safely, then format
            df_kpi[c] = pd.to_datetime(df_kpi[c], errors="coerce").dt.time.apply(lambda t: t.strftime("%H:%M:%S") if pd.notna(t) else None)

    st.subheader("Loading Durations Status")
    
    # Apply truck_condition filter if specified
    if truck_condition and "Truck_Condition" in df_kpi.columns:
        df_kpi = df_kpi[df_kpi["Truck_Condition"] == truck_condition]
    
    # Sort and prepare display
    df_view = df_kpi[display_cols].sort_values(["Product_Group", "Date", "Truck_Plate_Number"]).reset_index(drop=True)
    
    # Check if there are any validation errors
    has_errors = False
    error_count = 0
    if "Is_Valid_Order" in df_view.columns:
        has_errors = (~df_view["Is_Valid_Order"]).any()
        error_count = (~df_view["Is_Valid_Order"]).sum()
        if has_errors:
            st.warning(f"⚠️ {error_count} entries have incorrect timestamp order (highlighted in red)")
    
    # Remove validation columns from display (but keep them for styling reference)
    display_cols_final = [c for c in display_cols if c not in ["Is_Valid_Order", "Order_Error"]]
    
    # Create display dataframe
    df_display = df_view[display_cols_final].copy()
    
    # Format numeric columns to 2 decimal places in display
    numeric_cols = ["Waiting_min", "Loading_min", "Total_Weight_MT", "Loading_Rate_min/MT", "Loading_Rate_MT/Hour"]
    for col in numeric_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) and isinstance(x, (int, float)) else x)
    
    # Add error flag column at the beginning if there are errors
    if has_errors and "Order_Error" in df_view.columns:
        df_display.insert(0, "⚠️ Error", df_view["Order_Error"].fillna(""))
    
    # Apply styling for invalid rows using the original df_view with validation columns
    def highlight_invalid_rows(row):
        # Get the corresponding validation status from df_view
        idx = row.name
        if idx < len(df_view) and "Is_Valid_Order" in df_view.columns:
            if df_view.loc[idx, "Is_Valid_Order"] == False:
                return ['background-color: #ffcccc; font-weight: bold;'] * len(row)  # Red background and bold text
        return [''] * len(row)
    
    n_rows = len(df_display)
    
    # Style and display
    styled_df = df_display.style.apply(highlight_invalid_rows, axis=1)
    st.dataframe(styled_df, hide_index=True, use_container_width=True)
