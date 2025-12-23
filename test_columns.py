#!/usr/bin/env python3
"""Quick test to see what columns are in the raw sheets."""
import pandas as pd
from config.config import SPREADSHEET_ID, SHEET_GIDS

def _sheet_csv_url(gid: str):
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"

print("\n=== RAW COLUMNS FROM SHEETS ===\n")

for sheet_name in ['security', 'driver', 'status', 'logistic']:
    url = _sheet_csv_url(SHEET_GIDS[sheet_name])
    df = pd.read_csv(url, dtype=str, keep_default_na=False, nrows=5)
    print(f"\n{sheet_name.upper()} sheet:")
    print(f"  Columns: {list(df.columns)}")
    print(f"  First row sample: {df.iloc[0].to_dict() if len(df) > 0 else 'EMPTY'}")
