# data/processor.py
import pandas as pd

# column renames & maps (from your spec)
SECURITY_RENAME = {
    "ស្លាកលេខឡាន": "Truck_Plate_Number",
    "បរិមាណផ្ទុកទំនិញ": "Truck_Load_Capacity_by_Security",
    "អ្នកកំពុងស្កេនចេញ ឬ ចូល?": "Scan_In_or_Out",
    "អ្នកកមកឡើង ឬ ទម្លាក់​​ឥវ៉ាន់": "Coming_to_Upload_or_Unload"
}
DRIVER_RENAME = {
    "ឈ្មោះ": "Driver_Name",
    "ស្លាកលេខឡាន": "Truck_Plate_Number",
    "លេខទូរស័ព្វ": "Phone_Number",
    "បរិមាណផ្ទុកទំនិញគិតជាតោន": "Truck_Load_Capacity_by_Driver"
}
STATUS_RENAME = {
    "ស្លាកលេខឡាន": "Truck_Plate_Number",
    "ប្រភេទទំនិញ": "Product_Group"
}
LOGISTIC_RENAME = {
    "ប្រភេទទំនិញ": "Product_Group",
    "ស្លាកលេខឡាន": "Truck_Plate_Number",
    "Total Weight (MT) ": "Total_Weight_MT",
    "Outbound Delivery Nº": "Outbound_Delivery_No"
}

gate_map = {"​ចូល": "Gate_in", "ចេញ": "Gate_out"}
load_map = {"ឡើង ទំនិញ": "Uploading", "ទម្លាក់ ទំនិញ": "Unloading"}
product_map = {
    "ទីប ជ្រុង ទីបមូល": "Pipe",
    "ដំរ៉ូឡូ ជម្រៀក": "Coil",
    "ដែកសសៃ ដែកកង និង ដែក I & H": "Trading",
    "ស័ង្កសី": "Roofing",
    "ស័ង្កសី PU": "PU",
    "Other": "Other"
}
status_map_full = {
    "ចាប់ផ្តើមឡើងឬទម្លាក់ទំនិញ​ /Start Loading": "Start_Loading",
    "ឡើងឬទម្លាក់ទំនិញ​រួចរាល់ /Completed": "Completed",
    "មកដល់ច្រករង់ចាំ /Arrival": "Arrival"
}

def clean_sheet_dfs(dfs: dict):
    """
    Input: dict of raw dfs from loader (security, driver, status, logistic)
    Returns: cleaned dict (same keys) with renamed columns, mapping applied, timestamps parsed.
    """
    df_security = dfs['security'].rename(columns=SECURITY_RENAME)
    df_driver = dfs['driver'].rename(columns=DRIVER_RENAME)
    df_status = dfs['status'].rename(columns=STATUS_RENAME)
    df_logistic = dfs['logistic'].rename(columns=LOGISTIC_RENAME)

    # parse timestamps
    for df in (df_security, df_driver, df_status, df_logistic):
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

    # apply map replacements safely
    if "Scan_In_or_Out" in df_security.columns:
        df_security["Scan_In_or_Out"] = df_security["Scan_In_or_Out"].replace(gate_map)

    if "Coming_to_Upload_or_Unload" in df_security.columns:
        df_security["Coming_to_Upload_or_Unload"] = df_security["Coming_to_Upload_or_Unload"].replace(load_map)

    if "Product_Group" in df_status.columns:
        df_status["Product_Group"] = df_status["Product_Group"].replace(product_map)

    if "Product_Group" in df_logistic.columns:
        df_logistic["Product_Group"] = df_logistic["Product_Group"].replace(product_map)

    if "Status" in df_status.columns:
        df_status["Status"] = df_status["Status"].replace(status_map_full)

    return {
        'security': df_security,
        'driver': df_driver,
        'status': df_status,
        'logistic': df_logistic
    }
