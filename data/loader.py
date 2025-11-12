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
    return {
        'security': load_sheet_by_gid(SHEET_GIDS['security']),
        'driver': load_sheet_by_gid(SHEET_GIDS['driver']),
        'status': load_sheet_by_gid(SHEET_GIDS['status']),
        'logistic': load_sheet_by_gid(SHEET_GIDS['logistic']),
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
