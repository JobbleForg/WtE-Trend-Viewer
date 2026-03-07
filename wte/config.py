"""
Application-wide constants and small utility helpers.
"""

import os

NUM_SERIES = 10
MAX_CHARTS = 8
INITIAL_VISIBLE = 4
DEFAULT_HEIGHT_PX = 300

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LAST_SESSION_DIR = os.path.join(_APP_DIR, "_last_session")
TAG_DATA_FILE = os.path.join(_APP_DIR, "tag_manager_data.json")

WIDTH_OPTIONS = [
    {"label": "Quarter", "value": "quarter"},
    {"label": "Half", "value": "half"},
    {"label": "Full", "value": "full"},
]


def num_or_none(val):
    """Coerce a value to float, returning None for blanks / NaN / errors."""
    import pandas as pd
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, str) and val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
