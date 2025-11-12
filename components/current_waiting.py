# components/current_waiting.py
import streamlit as st
import pandas as pd

def show_current_waiting(df_security, df_status, df_driver, product_filter=None, upload_type=None, selected_date=None):
    """
    Show trucks currently waiting (Status = Arrival and not yet started loading)
    """

    for df in (df_security, df_status, df_driver):
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

    now = pd.Timestamp.now()

    # Get Arrival and Start_Loading times
    arrivals = df_status[df_status["Status"] == "Arrival"].groupby("Truck_Plate_Number")["Timestamp"].min().rename("Arrival_Time")
    starts = df_status[df_status["Status"] == "Start_Loading"].groupby("Truck_Plate_Number")["Timestamp"].min().rename("Start_Loading_Time")

    waiting = arrivals.to_frame().join(starts, how="left")
    waiting = waiting[(waiting["Start_Loading_Time"].isna()) | (waiting["Start_Loading_Time"] > now)]

    # Merge extra info
    sec_unique = df_security[["Truck_Plate_Number", "Coming_to_Upload_or_Unload"]].drop_duplicates("Truck_Plate_Number").set_index("Truck_Plate_Number")
    waiting = waiting.join(sec_unique, how="left")

    drv = df_driver.sort_values("Timestamp").groupby("Truck_Plate_Number").last()[["Driver_Name", "Phone_Number"]]
    waiting = waiting.join(drv, how="left")

    prod_stat = df_status.groupby("Truck_Plate_Number")["Product_Group"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else None)
    waiting = waiting.join(prod_stat.rename("Product_Group"), how="left")

    # Filters
    if product_filter:
        waiting = waiting[waiting["Product_Group"].isin(product_filter)]
    if upload_type:
        waiting = waiting[waiting["Coming_to_Upload_or_Unload"] == upload_type]
    if selected_date:
        waiting = waiting[pd.to_datetime(waiting["Arrival_Time"]).dt.date == selected_date]

    # Calculate waiting time
    waiting["Waiting_min"] = (pd.Timestamp.now() - waiting["Arrival_Time"]) / pd.Timedelta(minutes=1)

    # Reorder columns
    cols = [
        "Product_Group",
        "Coming_to_Upload_or_Unload",
        "Truck_Plate_Number",
        "Arrival_Time",
        "Waiting_min",
        "Driver_Name",
        "Phone_Number"
    ]
    waiting = waiting.reset_index()[cols]

    # Display
    st.subheader("Current Waiting Trucks")
    if waiting.empty:
        st.info("No current waiting trucks for the selected filters.")
    else:
        st.dataframe(waiting.sort_values("Waiting_min", ascending=False).reset_index(drop=True), hide_index=True)
