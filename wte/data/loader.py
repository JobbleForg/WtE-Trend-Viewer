"""
Excel data loading: load_sheet_data(), try_load_tag_refs(), tag_label().
"""

import pandas as pd

from wte.config import num_or_none


def load_sheet_data(filepath, sheet_name):
    """Load a single sheet from an Excel file, parse Time column."""
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=0)
    df.rename(columns={df.columns[0]: "Time"}, inplace=True)
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df.dropna(subset=["Time"], inplace=True)
    df.sort_values("Time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def try_load_tag_refs(filepath):
    """Parse the 'Tag Refs' sheet for tag metadata and chart packages."""
    tag_map = {}
    chart_packages = []
    try:
        raw = pd.read_excel(filepath, sheet_name="Tag Refs", header=None)
    except Exception:
        return tag_map, chart_packages

    for i in range(8, min(28, len(raw))):
        row = raw.iloc[i]
        friendly_name = row.iloc[4] if len(row) > 4 else None
        tag_code = row.iloc[5] if len(row) > 5 else None
        if pd.isna(tag_code) or str(tag_code).strip() == "":
            continue
        tag_code = str(tag_code).strip()
        decimals = row.iloc[11] if len(row) > 11 and not pd.isna(row.iloc[11]) else 1
        units = str(row.iloc[12]).strip() if len(row) > 12 and not pd.isna(row.iloc[12]) else ""
        y_highs = [
            num_or_none(row.iloc[15]) if len(row) > 15 else None,
            num_or_none(row.iloc[18]) if len(row) > 18 else None,
        ]
        y_lows = [
            num_or_none(row.iloc[16]) if len(row) > 16 else None,
            num_or_none(row.iloc[19]) if len(row) > 19 else None,
        ]
        tag_map[tag_code] = {
            "name": str(friendly_name).strip() if not pd.isna(friendly_name) else tag_code,
            "units": units,
            "decimals": int(decimals) if not pd.isna(decimals) else 1,
            "y_high": next((v for v in y_highs if v is not None), None),
            "y_low": next((v for v in y_lows if v is not None), None),
        }

    i = 31
    while i < min(49, len(raw)):
        row = raw.iloc[i]
        chart_num = row.iloc[3] if len(row) > 3 else None
        if pd.isna(chart_num) or str(chart_num).strip() == "":
            i += 1
            continue
        left_name = str(row.iloc[4]).strip() if len(row) > 4 and not pd.isna(row.iloc[4]) else ""
        right_name = str(row.iloc[5]).strip() if len(row) > 5 and not pd.isna(row.iloc[5]) else ""
        right_name_2 = ""
        if i + 1 < len(raw):
            next_row = raw.iloc[i + 1]
            if len(next_row) > 3 and pd.isna(next_row.iloc[3]):
                r2 = next_row.iloc[5] if len(next_row) > 5 else None
                if r2 and not pd.isna(r2) and str(r2).strip():
                    right_name_2 = str(r2).strip()
                i += 1
        if left_name or right_name:
            chart_packages.append({
                "num": str(chart_num).strip(),
                "tags": [left_name, right_name, right_name_2],
            })
        i += 1

    return tag_map, chart_packages


def tag_label(code, tag_map):
    """Build a human-readable label for a tag code."""
    if code in tag_map:
        info = tag_map[code]
        unit_str = f" [{info['units']}]" if info["units"] else ""
        return f"{code} - {info['name']}{unit_str}"
    return code
