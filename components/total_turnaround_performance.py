# components/total_turnaround_performance.py
import streamlit as st
import pandas as pd
from config.config import LOCAL_TZ


def show_total_turnaround_performance(dfs, df_kpi, start_date=None, end_date=None, product_selected=None, upload_type=None, truck_condition=None):
    """
    Show Total Turnaround Performance by Truck.
    
    Columns:
    - Date
    - Truck_Plate_Number
    - Total_Weight_MT (sum across products)
    - Count Product (distinct products)
    - Driver in Time (from driver sheet)
    - Max Time Doc (latest logistic timestamp per truck)
    - Documentation Time (Max Time Doc - Driver in Time)
    - Gate in time (first security timestamp)
    - Gate out time (last security timestamp)
    - Total turnaround (Gate out - Gate in)
    - Waiting time (from KPI)
    - Loading time (from KPI)
    - Processing time (Waiting + Loading + Documentation)
    - Dwelling time (Total turnaround - Processing)
    - Phone_Number
    """
    
    st.subheader("📊 Total Turnaround Performance by Truck")
    
    if df_kpi.empty:
        st.info("No data available for the selected date range and filters.")
        return
    
    df_security = dfs['security']
    df_driver = dfs['driver']
    df_logistic = dfs['logistic']
    
    # Ensure timestamps are datetime
    for df in (df_security, df_driver, df_logistic):
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    
    # Start with KPI data (already filtered by date range and products)
    # Aggregate per truck (combine all products)
    if df_kpi.empty:
        st.info("No KPI data available.")
        return
    
    # Group by Truck + Date to get truck-level metrics
    agg_dict = {
        "Date": "first",
        "Waiting_min": "sum",  # Sum waiting across products
        "Loading_min": "sum",  # Sum loading across products
        "Product_Group": lambda x: x.nunique()  # Count distinct products
    }
    
    # Aggregate per truck per date
    truck_perf = df_kpi.groupby("Truck_Plate_Number").agg(agg_dict).reset_index()
    truck_perf = truck_perf.rename(columns={"Product_Group": "Count_Product"})
    
    # --- Get Total_Weight_MT per truck (sum across products) ---
    if "Total_Weight_MT" in df_logistic.columns and "Truck_Plate_Number" in df_logistic.columns:
        # Filter logistic by date range
        df_logistic["_Date"] = df_logistic["Timestamp"].dt.date
        
        if start_date and end_date:
            df_log_filtered = df_logistic[(df_logistic["_Date"] >= start_date) & (df_logistic["_Date"] <= end_date)]
        elif start_date:
            df_log_filtered = df_logistic[df_logistic["_Date"] >= start_date]
        elif end_date:
            df_log_filtered = df_logistic[df_logistic["_Date"] <= end_date]
        else:
            df_log_filtered = df_logistic.copy()
        
        # Apply product filter if specified
        if product_selected and "Product_Group" in df_log_filtered.columns:
            df_log_filtered = df_log_filtered[df_log_filtered["Product_Group"].isin(product_selected)]
        
        # Apply truck condition filter
        if truck_condition and truck_condition != "All" and "Truck_Condition" in df_log_filtered.columns:
            df_log_filtered = df_log_filtered[df_log_filtered["Truck_Condition"] == truck_condition]
        
        weight_per_truck = (
            df_log_filtered.groupby("Truck_Plate_Number")["Total_Weight_MT"]
            .apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
            .reset_index()
        )
        truck_perf = truck_perf.merge(weight_per_truck, on="Truck_Plate_Number", how="left")
    else:
        truck_perf["Total_Weight_MT"] = None
    
    # --- Driver in Time (earliest driver timestamp per truck IN DATE RANGE) ---
    if "Timestamp" in df_driver.columns and "Truck_Plate_Number" in df_driver.columns:
        # Filter driver data by date range
        df_driver["_Date"] = df_driver["Timestamp"].dt.date
        
        if start_date and end_date:
            df_driver_filtered = df_driver[(df_driver["_Date"] >= start_date) & (df_driver["_Date"] <= end_date)]
        elif start_date:
            df_driver_filtered = df_driver[df_driver["_Date"] >= start_date]
        elif end_date:
            df_driver_filtered = df_driver[df_driver["_Date"] <= end_date]
        else:
            df_driver_filtered = df_driver.copy()
        
        if not df_driver_filtered.empty:
            driver_time = df_driver_filtered.groupby("Truck_Plate_Number")["Timestamp"].min().rename("Driver_in_Time").reset_index()
            truck_perf = truck_perf.merge(driver_time, on="Truck_Plate_Number", how="left")
        else:
            truck_perf["Driver_in_Time"] = pd.NaT
    else:
        truck_perf["Driver_in_Time"] = pd.NaT
    
    # --- Max Time Doc (latest logistic timestamp per truck) ---
    if "Timestamp" in df_logistic.columns and "Truck_Plate_Number" in df_logistic.columns:
        # Use filtered logistic data
        if 'df_log_filtered' in locals():
            max_doc_time = df_log_filtered.groupby("Truck_Plate_Number")["Timestamp"].max().rename("Max_Time_Doc").reset_index()
        else:
            max_doc_time = df_logistic.groupby("Truck_Plate_Number")["Timestamp"].max().rename("Max_Time_Doc").reset_index()
        truck_perf = truck_perf.merge(max_doc_time, on="Truck_Plate_Number", how="left")
    else:
        truck_perf["Max_Time_Doc"] = pd.NaT
    
    # --- Documentation Time (Max Time Doc - Driver in Time) in minutes ---
    def calc_doc_time(row):
        if pd.notna(row["Max_Time_Doc"]) and pd.notna(row["Driver_in_Time"]):
            return (row["Max_Time_Doc"] - row["Driver_in_Time"]) / pd.Timedelta(minutes=1)
        return None
    
    truck_perf["Documentation_Time_min"] = truck_perf.apply(calc_doc_time, axis=1)
    
    # --- Gate in time (first security scan IN DATE RANGE) ---
    if "Timestamp" in df_security.columns and "Truck_Plate_Number" in df_security.columns:
        # Filter security data by date range
        df_security["_Date"] = df_security["Timestamp"].dt.date
        
        if start_date and end_date:
            df_security_filtered = df_security[(df_security["_Date"] >= start_date) & (df_security["_Date"] <= end_date)]
        elif start_date:
            df_security_filtered = df_security[df_security["_Date"] >= start_date]
        elif end_date:
            df_security_filtered = df_security[df_security["_Date"] <= end_date]
        else:
            df_security_filtered = df_security.copy()
        
        if not df_security_filtered.empty:
            gate_in = df_security_filtered.groupby("Truck_Plate_Number")["Timestamp"].min().rename("Gate_in_Time").reset_index()
            truck_perf = truck_perf.merge(gate_in, on="Truck_Plate_Number", how="left")
        else:
            truck_perf["Gate_in_Time"] = pd.NaT
    else:
        truck_perf["Gate_in_Time"] = pd.NaT
    
    # --- Gate out time (last security scan IN DATE RANGE) ---
    if "Timestamp" in df_security.columns and "Truck_Plate_Number" in df_security.columns:
        # Use the same filtered security data from Gate_in_Time
        if 'df_security_filtered' in locals() and not df_security_filtered.empty:
            gate_out = df_security_filtered.groupby("Truck_Plate_Number")["Timestamp"].max().rename("Gate_out_Time").reset_index()
            truck_perf = truck_perf.merge(gate_out, on="Truck_Plate_Number", how="left")
        else:
            truck_perf["Gate_out_Time"] = pd.NaT
    else:
        truck_perf["Gate_out_Time"] = pd.NaT
    
    # --- Total turnaround (Gate out - Gate in) in minutes ---
    def calc_turnaround(row):
        if pd.notna(row["Gate_out_Time"]) and pd.notna(row["Gate_in_Time"]):
            return (row["Gate_out_Time"] - row["Gate_in_Time"]) / pd.Timedelta(minutes=1)
        return None
    
    truck_perf["Total_Turnaround_min"] = truck_perf.apply(calc_turnaround, axis=1)
    
    # --- Processing time (Waiting + Loading + Documentation) ---
    def calc_processing(row):
        total = 0
        count = 0
        if pd.notna(row.get("Waiting_min")):
            total += row["Waiting_min"]
            count += 1
        if pd.notna(row.get("Loading_min")):
            total += row["Loading_min"]
            count += 1
        if pd.notna(row.get("Documentation_Time_min")):
            total += row["Documentation_Time_min"]
            count += 1
        return total if count > 0 else None
    
    truck_perf["Processing_Time_min"] = truck_perf.apply(calc_processing, axis=1)
    
    # --- Dwelling time (Total turnaround - Processing) ---
    def calc_dwelling(row):
        if pd.notna(row.get("Total_Turnaround_min")) and pd.notna(row.get("Processing_Time_min")):
            return row["Total_Turnaround_min"] - row["Processing_Time_min"]
        return None
    
    truck_perf["Dwelling_Time_min"] = truck_perf.apply(calc_dwelling, axis=1)
    
    # --- Phone Number ---
    if "Phone_Number" in df_driver.columns and "Truck_Plate_Number" in df_driver.columns:
        phone_map = df_driver.groupby("Truck_Plate_Number")["Phone_Number"].first().reset_index()
        truck_perf = truck_perf.merge(phone_map, on="Truck_Plate_Number", how="left")
    else:
        truck_perf["Phone_Number"] = None
    
    # --- Apply upload_type filter (from security Coming_to_Load_or_Unload) ---
    if upload_type and "Coming_to_Load_or_Unload" in df_security.columns:
        upload_map = df_security.groupby("Truck_Plate_Number")["Coming_to_Load_or_Unload"].first().reset_index()
        truck_perf = truck_perf.merge(upload_map, on="Truck_Plate_Number", how="left")
        truck_perf = truck_perf[truck_perf["Coming_to_Load_or_Unload"] == upload_type]
    
    # Select and order columns for display
    display_cols = [
        "Date",
        "Truck_Plate_Number",
        "Total_Weight_MT",
        "Count_Product",
        "Driver_in_Time",
        "Max_Time_Doc",
        "Documentation_Time_min",
        "Gate_in_Time",
        "Gate_out_Time",
        "Total_Turnaround_min",
        "Waiting_min",
        "Loading_min",
        "Processing_Time_min",
        "Dwelling_Time_min",
        "Phone_Number"
    ]
    
    # Keep only existing columns
    display_cols = [col for col in display_cols if col in truck_perf.columns]
    df_display = truck_perf[display_cols].sort_values(["Date", "Truck_Plate_Number"], ascending=[False, True]).reset_index(drop=True)
    
    # Format display
    df_display["Total_Weight_MT"] = df_display["Total_Weight_MT"].apply(
        lambda x: f"{x:.2f}" if pd.notna(x) else ""
    )
    
    # Format time columns to show only time (HH:MM:SS)
    for time_col in ["Driver_in_Time", "Max_Time_Doc", "Gate_in_Time", "Gate_out_Time"]:
        if time_col in df_display.columns:
            df_display[time_col] = df_display[time_col].apply(
                lambda x: x.strftime('%H:%M:%S') if pd.notna(x) else ""
            )
    
    for col in ["Documentation_Time_min", "Total_Turnaround_min", "Waiting_min", "Loading_min", "Processing_Time_min", "Dwelling_Time_min"]:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda x: f"{x:.1f}" if pd.notna(x) else ""
            )
    
    # Show summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_trucks = len(df_display)
        st.metric("Total Trucks", total_trucks)
    with col2:
        avg_turnaround = pd.to_numeric(truck_perf["Total_Turnaround_min"], errors="coerce").mean()
        st.metric("Avg Turnaround (min)", f"{avg_turnaround:.1f}" if pd.notna(avg_turnaround) else "N/A")
    with col3:
        avg_processing = pd.to_numeric(truck_perf["Processing_Time_min"], errors="coerce").mean()
        st.metric("Avg Processing (min)", f"{avg_processing:.1f}" if pd.notna(avg_processing) else "N/A")
    with col4:
        avg_dwelling = pd.to_numeric(truck_perf["Dwelling_Time_min"], errors="coerce").mean()
        st.metric("Avg Dwelling (min)", f"{avg_dwelling:.1f}" if pd.notna(avg_dwelling) else "N/A")
    
    # Display table
    st.dataframe(df_display, use_container_width=True, height=400)
    
    # Download button
    csv = df_display.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"total_turnaround_performance_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
