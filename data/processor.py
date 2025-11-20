# data/processor.py
import pandas as pd
import re
from config.config import LOCAL_TZ

# ---------------- NORMALIZE ----------------
def normalize_plate(x):
    """
    Normalize truck plate strings to a canonical format:
    - uppercase
    - trim spaces
    - replace separators (space, dot, colon, underscore, slash…) with hyphen
    - collapse multiple hyphens into one
    """
    if pd.isna(x):
        return x
    x = str(x).upper().strip()
    x = re.sub(r"[ ._:;/\\]+", "-", x)   # replace separators with '-'
    x = re.sub(r"-+", "-", x)            # collapse multiple hyphens
    x = x.strip("-")                     # remove leading/trailing hyphens
    return x

def normalize_khmer_text(x):
    if pd.isna(x):
        return x
    x = str(x).strip()

    # Remove zero-width spaces, joiners, variation selectors, etc.
    x = re.sub(r"[\u200B-\u200D\uFE00-\uFE0F]", "", x)

    # Collapse double spaces
    x = re.sub(r"\s+", " ", x)

    return x


# ---------------- RENAME MAPS ----------------
SECURITY_RENAME = {
    "ស្លាកលេខឡាន": "Truck_Plate_Number",
    "បរិមាណផ្ទុកទំនិញ": "Truck_Load_Capacity_by_Security",
    "អ្នកកំពុងស្កេនចេញ ឬ ចូល?": "Scan_In_or_Out",
    "អ្នកកមកឡើង ឬ ទម្លាក់​​ឥវ៉ាន់": "Coming_to_Load_or_Unload"
}

DRIVER_RENAME = {
    "ឈ្មោះ": "Driver_Name",
    "ស្លាកលេខឡាន": "Truck_Plate_Number",   # ← THIS ONE MUST BE THIS
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


# ---------------- CLEAN MAPS ----------------
gate_map = {
    "ចូល": "Gate_in",
    "ចេញ": "Gate_out"
}

load_map = {
    "ឡើង ទំនិញ": "Loading",
    "ទម្លាក់ ទំនិញ": "Unloading"
}

product_map = {
    "ទីប ជ្រុង ទីបមូល": "Pipe",
    "ដំរ៉ូឡូ ជម្រៀក": "Coil",
    "ដំរ៉ូឡូ": "Coil",
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


# ---------------- PROCESS FUNCTION ----------------
def clean_sheet_dfs(dfs: dict):
    """
    Standard cleaning:
      - Rename fields
      - Normalize truck plates
      - Normalize Khmer product names
      - Apply maps
      - Use original timezone logic (no changes)
    """

    # Copy & rename
    df_security = dfs['security'].rename(columns=SECURITY_RENAME)
    df_driver = dfs['driver'].rename(columns=DRIVER_RENAME)
    df_status = dfs['status'].rename(columns=STATUS_RENAME)
    df_logistic = dfs['logistic'].rename(columns=LOGISTIC_RENAME)

    # -------------------------------
    # Normalize truck plate numbers
    # -------------------------------
    for df in (df_security, df_driver, df_status, df_logistic):
        if "Truck_Plate_Number" in df.columns:
            df["Truck_Plate_Number"] = df["Truck_Plate_Number"].apply(normalize_plate)

    # -------------------------------
    # ORIGINAL TIMEZONE LOGIC
    # -------------------------------
    for df in (df_security, df_driver, df_status, df_logistic):
        if "Timestamp" in df.columns:
            ts = pd.to_datetime(df["Timestamp"], errors="coerce")
            df["Timestamp"] = ts.dt.tz_localize(
                LOCAL_TZ,
                nonexistent='shift_forward',
                ambiguous='NaT'
            )

    # -------------------------------
    # Normalize Khmer Product_Group
    # (Fix invisible Unicode: zero-width, joiners)
    # -------------------------------
    if "Product_Group" in df_status.columns:
        df_status["Product_Group"] = df_status["Product_Group"].apply(normalize_khmer_text)

    if "Product_Group" in df_logistic.columns:
        df_logistic["Product_Group"] = df_logistic["Product_Group"].apply(normalize_khmer_text)

    # -------------------------------
    # Apply mappings
    # -------------------------------
    if "Scan_In_or_Out" in df_security.columns:
        df_security["Scan_In_or_Out"] = df_security["Scan_In_or_Out"].replace(gate_map)

    if "Coming_to_Load_or_Unload" in df_security.columns:
        df_security["Coming_to_Load_or_Unload"] = df_security["Coming_to_Load_or_Unload"].replace(load_map)

    if "Product_Group" in df_status.columns:
        df_status["Product_Group"] = df_status["Product_Group"].replace(product_map)

    if "Product_Group" in df_logistic.columns:
        df_logistic["Product_Group"] = df_logistic["Product_Group"].replace(product_map)

    if "Status" in df_status.columns:
        df_status["Status"] = df_status["Status"].replace(status_map_full)

    # -------------------------------
    # Return cleaned data
    # -------------------------------
    return {
        'security': df_security,
        'driver': df_driver,
        'status': df_status,
        'logistic': df_logistic
    }

