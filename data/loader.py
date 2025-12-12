# data/loader.py
import pandas as pd
from config.config import SPREADSHEET_ID, SHEET_GIDS
import streamlit as st

def _sheet_csv_url(gid: str):
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"

@st.cache_data(ttl=15)  # cache for 15 seconds (adjust)
def load_sheet_by_gid(gid: str):
    url = _sheet_csv_url(gid)
    return pd.read_csv(url)

@st.cache_data(ttl=15)
def load_all_sheets():
    # Force truck plate columns to be read as string to avoid numeric conversion
    # (e.g., "3A-1111" → "0.00E+00" in Excel/GoogleSheets)
    security_url = _sheet_csv_url(SHEET_GIDS['security'])
    driver_url = _sheet_csv_url(SHEET_GIDS['driver'])
    status_url = _sheet_csv_url(SHEET_GIDS['status'])
    logistic_url = _sheet_csv_url(SHEET_GIDS['logistic'])
    
    df_security = pd.read_csv(security_url, dtype=str, keep_default_na=False)
    df_driver = pd.read_csv(driver_url, dtype=str, keep_default_na=False)
    df_status = pd.read_csv(status_url, dtype=str, keep_default_na=False)
    df_logistic = pd.read_csv(logistic_url, dtype=str, keep_default_na=False)
    
    # Replace empty strings with NaN for proper handling
    for df in [df_security, df_driver, df_status, df_logistic]:
        df.replace('', pd.NA, inplace=True)
    
    return {
        'security': df_security,
        'driver': df_driver,
        'status': df_status,
        'logistic': df_logistic,
    }

def get_current_date_from_sheets(dfs: dict):
    # return the max date across Timestamp columns (date part)
    import pandas as pd
    max_dates = []
    for df in dfs.values():
        if "Timestamp" in df.columns:
            s = pd.to_datetime(df["Timestamp"], errors="coerce").dt.date
            if not s.dropna().empty:
                max_dates.append(s.max())
    if max_dates:
        return max(max_dates)
    return pd.to_datetime("today").date()
