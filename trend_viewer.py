"""
Waste-to-Energy Plant Trend Viewer
DCS-style trend display built with Dash + Plotly.
Dynamically loads data from any Excel file and displays resizable trend charts.
Each chart supports 10 series with shared Y-axes for matching units.
Charts can be added, removed, and resized.
"""

import os
import atexit
import base64
import glob
import json
import tempfile
from io import StringIO
import pandas as pd
from datetime import datetime, timedelta
from dash import Dash, dcc, html, Input, Output, State, callback_context, no_update, ALL, MATCH
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_SERIES = 10
MAX_CHARTS = 8
INITIAL_VISIBLE = 4


# ---------------------------------------------------------------------------
# Temp-file cleanup (Issue #3)
# ---------------------------------------------------------------------------

def _cleanup_temp_files():
    """Remove any leftover wte_upload_* temp files on shutdown."""
    pattern = os.path.join(tempfile.gettempdir(), "wte_upload_*")
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass


atexit.register(_cleanup_temp_files)


# ---------------------------------------------------------------------------
# Persistent tag-manager data (survives reboots / updates)
# ---------------------------------------------------------------------------

_TAG_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "tag_manager_data.json")


def _load_tag_manager_data():
    """Load saved tag nicknames and custom units from the local JSON file."""
    if os.path.isfile(_TAG_DATA_FILE):
        try:
            with open(_TAG_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("nicknames", {}), data.get("custom_units", [])
        except (json.JSONDecodeError, OSError):
            return {}, []
    return {}, []


def _save_tag_manager_data(nicknames, custom_units):
    """Write tag nicknames and custom units to the local JSON file."""
    payload = {"nicknames": nicknames or {}, "custom_units": custom_units or []}
    try:
        with open(_TAG_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


# Pre-load persisted data so stores can be initialised with it
_INIT_NICKNAMES, _INIT_CUSTOM_UNITS = _load_tag_manager_data()


def _num_or_none(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, str) and val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def load_sheet_data(filepath, sheet_name):
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=0)
    df.rename(columns={df.columns[0]: "Time"}, inplace=True)
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df.dropna(subset=["Time"], inplace=True)
    df.sort_values("Time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def try_load_tag_refs(filepath):
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
            _num_or_none(row.iloc[15]) if len(row) > 15 else None,
            _num_or_none(row.iloc[18]) if len(row) > 18 else None,
        ]
        y_lows = [
            _num_or_none(row.iloc[16]) if len(row) > 16 else None,
            _num_or_none(row.iloc[19]) if len(row) > 19 else None,
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
    if code in tag_map:
        info = tag_map[code]
        unit_str = f" [{info['units']}]" if info["units"] else ""
        return f"{code} - {info['name']}{unit_str}"
    return code


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

BG_COLOR = "#0d1117"
PANEL_BG = "#161b22"
CHART_BG = "#0d1117"
GRID_COLOR = "#30363d"
TEXT_COLOR = "#c9d1d9"
ACCENT = "#58a6ff"
TRACE_COLORS = [
    "#58a6ff", "#3fb950", "#f0883e", "#bc8cff", "#f778ba",
    "#79c0ff", "#ffa657", "#7ee787", "#ff7b72", "#d2a8ff",
]
BORDER_COLOR = "#30363d"
MUTED_TEXT = "#8b949e"

LABEL_STYLE = {
    "color": TEXT_COLOR, "fontSize": "12px", "marginRight": "4px",
    "whiteSpace": "nowrap",
}
INPUT_STYLE = {
    "width": "65px", "backgroundColor": PANEL_BG, "color": TEXT_COLOR,
    "border": f"1px solid {BORDER_COLOR}", "borderRadius": "4px",
    "padding": "2px 6px", "fontSize": "12px", "textAlign": "center",
}
DROPDOWN_STYLE = {
    "width": "220px", "fontSize": "12px",
    "backgroundColor": PANEL_BG, "color": TEXT_COLOR,
}
BTN_STYLE = {
    "backgroundColor": "#21262d", "color": TEXT_COLOR,
    "border": f"1px solid {BORDER_COLOR}", "borderRadius": "4px",
    "padding": "4px 12px", "cursor": "pointer", "fontSize": "12px",
    "marginLeft": "4px",
}

WIDTH_OPTIONS = [
    {"label": "Quarter", "value": "quarter"},
    {"label": "Half", "value": "half"},
    {"label": "Full", "value": "full"},
]
DEFAULT_HEIGHT_PX = 300

LOCKED_ICON_STYLE = {
    "fontSize": "11px", "cursor": "pointer",
    "color": "#3fb950", "lineHeight": "1",
    "userSelect": "none", "textAlign": "center",
}
UNLOCKED_ICON_STYLE = {
    "fontSize": "11px", "cursor": "pointer",
    "color": MUTED_TEXT, "lineHeight": "1",
    "userSelect": "none", "textAlign": "center",
}

# ---------------------------------------------------------------------------
# Dash app
# ---------------------------------------------------------------------------

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "WtE Trend Viewer"


def make_chart_panel(chart_id):
    """Build a chart panel. All MAX_CHARTS panels are pre-created in the DOM."""
    cid = str(chart_id)
    hidden = chart_id > INITIAL_VISIBLE

    dropdown_rows = []
    for row_start in (1, 6):
        row_children = []
        for s in range(row_start, min(row_start + 5, NUM_SERIES + 1)):
            color_dot = TRACE_COLORS[s - 1]
            # Each series: label + vertical stack (lock on top, dropdown below) + Own checkbox
            row_children.extend([
                html.Span(f"S{s}", style={
                    **LABEL_STYLE,
                    "color": color_dot, "fontWeight": "bold",
                    "marginLeft": "8px" if s != row_start else "0",
                }),
                html.Div(style={
                    "display": "flex", "flexDirection": "column",
                    "alignItems": "center", "gap": "0px",
                }, children=[
                    html.Div(
                        id={"type": "lock-scale-btn", "chart": chart_id, "series": s},
                        children="\U0001F513",
                        n_clicks=0,
                        style=UNLOCKED_ICON_STYLE,
                        title="Lock Y-axis scale",
                    ),
                    dcc.Dropdown(
                        id={"type": "series-dd", "chart": chart_id, "series": s},
                        options=[], value=None,
                        placeholder=f"Series {s}", clearable=True,
                        style={**DROPDOWN_STYLE, "width": "150px"},
                        className="dark-dropdown",
                    ),
                ]),
                # Hidden store to hold the lock state (toggled by the button callback)
                dcc.Checklist(
                    id={"type": "lock-scale", "chart": chart_id, "series": s},
                    options=[{"label": "", "value": "lock"}],
                    value=[],
                    style={"display": "none"},
                    inline=True,
                ),
                dcc.Checklist(
                    id={"type": "own-scale", "chart": chart_id, "series": s},
                    options=[{"label": "Own", "value": "own"}],
                    value=[],
                    style={"fontSize": "10px", "color": MUTED_TEXT,
                           "display": "inline-flex", "alignItems": "center"},
                    className="own-scale-check",
                    inline=True,
                ),
            ])
        dropdown_rows.append(html.Div(style={
            "display": "flex", "alignItems": "center", "gap": "4px",
            "marginTop": "4px", "flexWrap": "wrap",
        }, children=row_children))

    return html.Div(
        id={"type": "chart-wrapper", "index": chart_id},
        style={
            "backgroundColor": PANEL_BG, "borderRadius": "8px",
            "border": f"1px solid {BORDER_COLOR}", "padding": "8px",
            "display": "none" if hidden else "flex",
            "flexDirection": "column",
            "flexBasis": "calc(50% - 5px)",
            "minWidth": "280px",
            "boxSizing": "border-box",
        },
        children=[
            # Title bar with controls
            html.Div(style={
                "display": "flex", "alignItems": "center", "gap": "8px",
                "marginBottom": "4px",
            }, children=[
                html.Span(f"Chart {cid}", style={
                    "color": TEXT_COLOR, "fontSize": "14px", "fontWeight": "bold",
                    "paddingLeft": "4px", "flex": "1",
                }),
                html.Span("W:", style={**LABEL_STYLE, "fontSize": "11px"}),
                dcc.Dropdown(
                    id={"type": "width-select", "index": chart_id},
                    options=WIDTH_OPTIONS, value="half", clearable=False,
                    style={**DROPDOWN_STYLE, "width": "80px", "fontSize": "11px"},
                    className="dark-dropdown",
                ),
                html.Span("H:", style={**LABEL_STYLE, "fontSize": "11px"}),
                dcc.Input(
                    id={"type": "height-select", "index": chart_id},
                    type="number", value=DEFAULT_HEIGHT_PX,
                    min=100, max=2000, step=50,
                    style={**INPUT_STYLE, "width": "60px", "fontSize": "11px"},
                    debounce=True,
                ),
                html.Span("px", style={**LABEL_STYLE, "fontSize": "10px",
                                        "color": MUTED_TEXT}),
                dcc.Checklist(
                    id={"type": "show-limits", "index": chart_id},
                    options=[{"label": "Limits", "value": "limits"}],
                    value=["limits"],
                    style={"fontSize": "10px", "color": MUTED_TEXT,
                           "display": "inline-flex", "alignItems": "center"},
                    className="own-scale-check",
                    inline=True,
                ),
                html.Button("\u2398 Copy CSV",
                            id={"type": "copy-csv-btn", "index": chart_id},
                            style={**BTN_STYLE, "color": "#d29922",
                                   "fontSize": "11px", "padding": "2px 10px"},
                            title="Copy visible data as CSV to clipboard"),
                html.Button("\U0001F513 Lock All",
                            id={"type": "lock-all-btn", "index": chart_id},
                            style={**BTN_STYLE, "color": MUTED_TEXT,
                                   "fontSize": "11px", "padding": "2px 10px"},
                            title="Lock / unlock all Y-axis scales on this chart"),
                html.Button("\U0001F517 Sync", id={"type": "sync-btn", "index": chart_id},
                            style={**BTN_STYLE, "color": "#58a6ff",
                                   "fontSize": "11px", "padding": "2px 10px"},
                            title="Sync all charts to this chart's time"),
                html.Button("\u2715", id={"type": "close-btn", "index": chart_id},
                            style={**BTN_STYLE, "color": "#f85149",
                                   "fontSize": "14px", "padding": "2px 8px"},
                            title="Close chart"),
            ]),
            # Graph
            dcc.Graph(
                id={"type": "graph", "index": chart_id},
                config={"displayModeBar": True, "scrollZoom": True},
                style={"height": f"{DEFAULT_HEIGHT_PX}px"},
            ),
            # Collapsible setup area toggle
            html.Div(style={"textAlign": "center", "marginTop": "2px"}, children=[
                html.Button(
                    "Setup \u25BC",
                    id={"type": "setup-toggle", "index": chart_id},
                    style={**BTN_STYLE, "fontSize": "10px", "padding": "1px 12px",
                           "color": MUTED_TEXT, "width": "100%"},
                    title="Show / hide chart setup controls",
                ),
            ]),
            # Collapsible setup area (Issue #15)
            html.Div(
                id={"type": "setup-area", "index": chart_id},
                style={"display": "block"},
                children=[
                    *dropdown_rows,
                    # Filter row for rolling mean (Issue #18)
                    html.Div(style={
                        "display": "flex", "alignItems": "center", "gap": "4px",
                        "marginTop": "4px", "flexWrap": "wrap",
                    }, children=[
                        html.Span("Filter:", style={
                            **LABEL_STYLE, "fontSize": "11px", "color": MUTED_TEXT,
                        }),
                    ] + [
                        item for s in range(1, NUM_SERIES + 1) for item in [
                            html.Span(f"S{s}", style={
                                "color": TRACE_COLORS[s - 1], "fontSize": "10px",
                                "fontWeight": "bold",
                                "marginLeft": "6px" if s > 1 else "0",
                            }),
                            dcc.Input(
                                id={"type": "filter-window", "chart": chart_id, "series": s},
                                type="number", value=1, min=1, max=9999,
                                placeholder="1",
                                style={**INPUT_STYLE, "width": "45px", "fontSize": "11px"},
                                debounce=True,
                            ),
                        ]
                    ]),
                    # Time controls
                    html.Div(style={
                        "display": "flex", "alignItems": "center", "gap": "8px",
                        "marginTop": "6px", "flexWrap": "wrap",
                    }, children=[
                        html.Span("Go to:", style=LABEL_STYLE),
                        dcc.Input(id={"type": "goto-date", "index": chart_id}, type="text",
                                  value="", placeholder="YYYY-MM-DD",
                                  style={**INPUT_STYLE, "width": "100px"}, debounce=True),
                        dcc.Input(id={"type": "goto-time", "index": chart_id}, type="text",
                                  value="00:00", placeholder="HH:MM",
                                  style={**INPUT_STYLE, "width": "60px"}, debounce=True),
                        html.Span("Window:", style={**LABEL_STYLE, "marginLeft": "12px"}),
                        dcc.Input(id={"type": "win-min", "index": chart_id}, type="number",
                                  value=60, style={**INPUT_STYLE, "width": "55px"}, debounce=True),
                        html.Span("min +", style=LABEL_STYLE),
                        dcc.Input(id={"type": "win-hr", "index": chart_id}, type="number",
                                  value=0, style={**INPUT_STYLE, "width": "45px"}, debounce=True),
                        html.Span("hr", style=LABEL_STYLE),
                        html.Span("Step:", style={**LABEL_STYLE, "marginLeft": "12px"}),
                        dcc.Input(id={"type": "step", "index": chart_id}, type="number",
                                  value=15, style={**INPUT_STYLE, "width": "55px"}, debounce=True),
                        html.Span("min", style=LABEL_STYLE),
                        html.Button("\u25C0", id={"type": "scroll-left", "index": chart_id},
                                    style=BTN_STYLE, title="Scroll left"),
                        html.Button("\u25B6", id={"type": "scroll-right", "index": chart_id},
                                    style=BTN_STYLE, title="Scroll right"),
                        html.Button("Load Area", id={"type": "load-area-btn", "index": chart_id},
                                    style={**BTN_STYLE, "color": "#f0883e",
                                           "marginLeft": "12px"},
                                    title="Load data for the visible area after zooming out"),
                        html.Button("Autoscale X", id={"type": "autoscale-x-btn", "index": chart_id},
                                    style={**BTN_STYLE, "color": "#3fb950",
                                           "marginLeft": "4px"},
                                    title="Reset X-axis to full data range (keeps Y-axes)"),
                    ]),
                ],
            ),
            dcc.Store(id={"type": "start-time", "index": chart_id}, data=None),
            dcc.Store(id={"type": "x-range", "index": chart_id}, data=None),
            dcc.Store(id={"type": "lock-all-state", "index": chart_id}, data=False),
            dcc.Store(id={"type": "csv-data", "index": chart_id}, data=""),
            html.Span(id={"type": "csv-clipboard-dummy", "index": chart_id},
                       style={"display": "none"}),
            dcc.Store(id={"type": "cursor-ts", "index": chart_id}, data=None),
            html.Div(
                id={"type": "cursor-readout", "index": chart_id},
                style={"display": "none"},
                children=[
                    html.Div(style={
                        "display": "flex", "alignItems": "center",
                        "backgroundColor": "#1c2129",
                        "border": f"1px solid {BORDER_COLOR}",
                        "borderRadius": "4px",
                        "padding": "4px 8px", "marginTop": "2px",
                    }, children=[
                        html.Span(
                            id={"type": "cursor-readout-text", "index": chart_id},
                            style={
                                "fontSize": "11px",
                                "fontFamily": "Consolas, monospace",
                                "color": TEXT_COLOR, "flex": "1",
                            },
                        ),
                        html.Button(
                            "\u2715 Clear",
                            id={"type": "cursor-clear-btn", "index": chart_id},
                            style={
                                **BTN_STYLE, "color": "#f85149",
                                "fontSize": "10px", "padding": "1px 8px",
                                "marginLeft": "8px", "flexShrink": "0",
                            },
                        ),
                    ]),
                ],
            ),
        ],
    )


# --- App layout ---

app.layout = html.Div(style={
    "backgroundColor": BG_COLOR, "minHeight": "100vh", "padding": "12px",
    "fontFamily": "'Segoe UI', Consolas, monospace",
}, children=[
    dcc.Store(id="temp-file-path", data=None),
    dcc.Store(id="session-data", storage_type="memory", data=None),
    dcc.Store(id="visible-charts", data=list(range(1, INITIAL_VISIBLE + 1))),
    dcc.Store(id="saved-setups", storage_type="local", data={}),
    dcc.Store(id="sync-state", data={"active": False, "master": None}),
    dcc.Store(id="tag-nicknames", storage_type="memory", data=_INIT_NICKNAMES),
    dcc.Store(id="custom-units", storage_type="memory", data=_INIT_CUSTOM_UNITS),
    dcc.Store(id="notes-text", storage_type="local", data=""),

    # Notes overlay panel (Issue #12)
    html.Div(
        id="notes-overlay",
        style={
            "display": "none",
            "position": "fixed", "top": "50%", "left": "50%",
            "transform": "translate(-50%, -50%)",
            "zIndex": 9999,
            "width": "500px", "maxWidth": "90vw",
            "backgroundColor": PANEL_BG,
            "border": f"2px solid {ACCENT}",
            "borderRadius": "10px",
            "boxShadow": "0 8px 32px rgba(0,0,0,0.6)",
            "padding": "0",
            "flexDirection": "column",
        },
        children=[
            # Title bar
            html.Div(style={
                "display": "flex", "alignItems": "center",
                "padding": "8px 12px",
                "borderBottom": f"1px solid {BORDER_COLOR}",
                "borderRadius": "10px 10px 0 0",
                "backgroundColor": "#1c2129",
            }, children=[
                html.Span("\U0001F4DD Notes", style={
                    "color": TEXT_COLOR, "fontSize": "14px",
                    "fontWeight": "bold", "flex": "1",
                }),
                html.Button("\u2715", id="notes-close-btn", style={
                    **BTN_STYLE, "color": "#f85149", "fontSize": "14px",
                    "padding": "2px 8px",
                }),
            ]),
            # Textarea
            dcc.Textarea(
                id="notes-textarea",
                value="",
                placeholder="Jot down observations, timestamps, suspected causes...",
                style={
                    "width": "100%", "minHeight": "250px",
                    "backgroundColor": "#0d1117",
                    "color": TEXT_COLOR, "border": "none",
                    "padding": "12px", "fontSize": "12px",
                    "fontFamily": "Consolas, monospace",
                    "resize": "vertical", "boxSizing": "border-box",
                    "borderRadius": "0 0 10px 10px",
                },
            ),
        ],
    ),

    # Header toolbar
    html.Div(style={
        "display": "flex", "alignItems": "center", "gap": "16px",
        "marginBottom": "4px", "padding": "0 8px", "flexWrap": "wrap",
    }, children=[
        html.H1("WtE Trend Viewer", style={
            "color": ACCENT, "fontSize": "22px", "margin": "0",
            "marginRight": "16px",
        }),
        dcc.Upload(
            id="file-upload",
            children=html.Button("Load File", style={
                **BTN_STYLE, "marginLeft": "0",
                "padding": "6px 16px", "fontSize": "13px",
            }),
            multiple=False, accept=".xlsx,.xls,.xlsm",
        ),
        html.Span(id="file-name-display", children="No file loaded",
                  style={"color": MUTED_TEXT, "fontSize": "12px"}),
        html.Span("Sheet:", style=LABEL_STYLE),
        dcc.Dropdown(
            id="sheet-select", options=[], value=None,
            placeholder="Select sheet...", clearable=False,
            style={**DROPDOWN_STYLE, "width": "200px"},
            className="dark-dropdown",
        ),
        html.Span("Package:", style={**LABEL_STYLE, "marginLeft": "8px"}),
        dcc.Dropdown(
            id="pkg-select",
            options=[{"label": "-- None --", "value": ""}],
            value="", clearable=False,
            style={**DROPDOWN_STYLE, "width": "280px"},
            className="dark-dropdown",
        ),
        html.Button("+ Add Chart", id="add-chart-btn", style={
            **BTN_STYLE, "marginLeft": "8px", "padding": "6px 14px",
            "fontSize": "13px", "color": "#3fb950",
        }),
        # --- Save / Load Setup controls ---
        html.Div(style={
            "display": "flex", "alignItems": "center", "gap": "6px",
            "marginLeft": "16px", "borderLeft": f"1px solid {BORDER_COLOR}",
            "paddingLeft": "16px",
        }, children=[
            html.Span("Setup:", style=LABEL_STYLE),
            dcc.Input(
                id="setup-name-input", type="text", value="",
                placeholder="Setup name...",
                style={**INPUT_STYLE, "width": "140px"},
                debounce=True,
            ),
            html.Button("Save", id="save-setup-btn", style={
                **BTN_STYLE, "color": "#3fb950", "padding": "4px 14px",
            }),
            dcc.Dropdown(
                id="load-setup-dropdown",
                options=[], value=None,
                placeholder="Load setup...", clearable=True,
                style={**DROPDOWN_STYLE, "width": "180px"},
                className="dark-dropdown",
            ),
            html.Button("Delete", id="delete-setup-btn", style={
                **BTN_STYLE, "color": "#f85149", "padding": "4px 10px",
            }),
        ]),
        html.Span(id="setup-status-msg", children="",
                  style={"color": MUTED_TEXT, "fontSize": "11px"}),
        html.Button("\U0001F4DD Notes", id="notes-toggle-btn", style={
            **BTN_STYLE, "marginLeft": "12px", "padding": "6px 14px",
            "fontSize": "13px", "color": "#d2a8ff",
        }, title="Open / close notes panel"),
    ]),

    # Data stats bar
    html.Div(id="data-stats", style={
        "padding": "4px 12px", "marginBottom": "8px",
        "color": MUTED_TEXT, "fontSize": "12px",
    }, children="Load an Excel file and select a data sheet to begin."),

    # Chart container — flexbox wrap
    html.Div(
        id="chart-container",
        style={
            "display": "flex", "flexWrap": "wrap", "gap": "10px",
        },
        children=[make_chart_panel(i) for i in range(1, MAX_CHARTS + 1)],
    ),

    # Tag Reference / Tag Manager — collapsible panel
    html.Div(style={"marginTop": "12px"}, children=[
        html.Button(
            id="tag-panel-toggle",
            children="Tag Manager \u25BC",
            style={
                **BTN_STYLE,
                "marginLeft": "0", "padding": "6px 16px",
                "fontSize": "13px", "color": ACCENT,
                "width": "auto",
            },
        ),
        html.Div(
            id="tag-panel",
            style={
                "display": "none",
                "backgroundColor": PANEL_BG,
                "borderRadius": "8px",
                "border": f"1px solid {BORDER_COLOR}",
                "padding": "12px",
                "marginTop": "6px",
            },
            children=[
                html.Div(style={
                    "display": "flex", "alignItems": "center",
                    "marginBottom": "8px", "flexWrap": "wrap", "gap": "8px",
                }, children=[
                    html.Span("Tag Manager", style={
                        "color": ACCENT, "fontSize": "14px",
                        "fontWeight": "bold",
                    }),
                    html.Span(
                        "  Set nicknames and units for loaded tags. "
                        "Changes appear on chart legends and Y-axis labels.",
                        style={"color": MUTED_TEXT, "fontSize": "11px",
                               "marginLeft": "12px"},
                    ),
                    html.Div(style={
                        "display": "flex", "alignItems": "center",
                        "gap": "4px", "marginLeft": "auto",
                    }, children=[
                        html.Span("Add unit:", style={
                            **LABEL_STYLE, "fontSize": "11px",
                        }),
                        dcc.Input(
                            id="custom-unit-input",
                            type="text",
                            placeholder="e.g. kPa",
                            style={**INPUT_STYLE, "width": "90px",
                                   "fontSize": "11px"},
                            debounce=False,
                        ),
                        html.Button("+", id="add-unit-btn", style={
                            **BTN_STYLE, "padding": "4px 10px",
                            "fontSize": "12px", "minWidth": "auto",
                        }),
                    ]),
                ]),
                # Table header
                html.Div(style={
                    "display": "grid",
                    "gridTemplateColumns": "1fr 1.5fr 1fr 1fr",
                    "gap": "6px",
                    "padding": "4px 0",
                    "borderBottom": f"1px solid {BORDER_COLOR}",
                    "marginBottom": "4px",
                }, children=[
                    html.Span("Tag Code", style={
                        "color": ACCENT, "fontSize": "11px",
                        "fontWeight": "bold",
                    }),
                    html.Span("Current Name", style={
                        "color": ACCENT, "fontSize": "11px",
                        "fontWeight": "bold",
                    }),
                    html.Span("Nickname", style={
                        "color": ACCENT, "fontSize": "11px",
                        "fontWeight": "bold",
                    }),
                    html.Span("Unit", style={
                        "color": ACCENT, "fontSize": "11px",
                        "fontWeight": "bold",
                    }),
                ]),
                # Tag rows container (populated dynamically)
                html.Div(id="tag-rows-container"),
            ],
        ),
    ]),
])

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

app.index_string = '''<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        .dark-dropdown .Select-control {
            background-color: ''' + PANEL_BG + ''' !important;
            border-color: ''' + BORDER_COLOR + ''' !important;
            color: ''' + TEXT_COLOR + ''' !important;
        }
        .dark-dropdown .Select-menu-outer {
            background-color: ''' + PANEL_BG + ''' !important;
            border-color: ''' + BORDER_COLOR + ''' !important;
        }
        .dark-dropdown .Select-option {
            background-color: ''' + PANEL_BG + ''' !important;
            color: ''' + TEXT_COLOR + ''' !important;
        }
        .dark-dropdown .Select-option.is-focused {
            background-color: #21262d !important;
        }
        .dark-dropdown .Select-value-label,
        .dark-dropdown .Select-placeholder {
            color: ''' + TEXT_COLOR + ''' !important;
        }
        .dark-dropdown input {
            color: ''' + TEXT_COLOR + ''' !important;
        }
        .dark-dropdown > div {
            background-color: ''' + PANEL_BG + ''' !important;
        }
        body { margin: 0; background-color: ''' + BG_COLOR + '''; }
        /* Disabled time controls styling for sync lock */
        input:disabled, button:disabled {
            opacity: 0.4 !important;
            cursor: not-allowed !important;
        }
        /* Own-scale checkbox styling */
        .own-scale-check label {
            color: ''' + MUTED_TEXT + ''' !important;
            font-size: 10px !important;
            cursor: pointer;
            margin: 0 !important;
            padding: 0 !important;
        }
        .own-scale-check input[type="checkbox"] {
            margin-right: 2px;
        }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>'''

# ---------------------------------------------------------------------------
# Callback: Add chart / close chart → update visibility
# ---------------------------------------------------------------------------

@app.callback(
    Output("visible-charts", "data", allow_duplicate=True),
    Output("sync-state", "data", allow_duplicate=True),
    Input("add-chart-btn", "n_clicks"),
    Input({"type": "close-btn", "index": ALL}, "n_clicks"),
    State("visible-charts", "data"),
    State("sync-state", "data"),
    prevent_initial_call=True,
)
def update_visible_charts(add_clicks, close_clicks_list, visible, sync_state):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update
    triggered = ctx.triggered[0]["prop_id"]

    new_visible = no_update
    if triggered == "add-chart-btn.n_clicks":
        for i in range(1, MAX_CHARTS + 1):
            if i not in visible:
                new_visible = visible + [i]
                break
    else:
        try:
            prop = json.loads(triggered.rsplit(".", 1)[0])
            chart_id = prop["index"]
            if chart_id in visible and len(visible) > 1:
                new_visible = [v for v in visible if v != chart_id]
        except Exception:
            pass

    # Reset sync if the master chart was closed
    new_sync = no_update
    if new_visible is not no_update and sync_state and sync_state.get("active"):
        if sync_state.get("master") not in new_visible:
            new_sync = {"active": False, "master": None}

    return new_visible, new_sync


# ---------------------------------------------------------------------------
# Callback: visibility store → update each panel's display style
# ---------------------------------------------------------------------------

for _i in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "chart-wrapper", "index": _i}, "style", allow_duplicate=True),
        Input("visible-charts", "data"),
        Input({"type": "width-select", "index": _i}, "value"),
        Input({"type": "height-select", "index": _i}, "value"),
        prevent_initial_call=True,
    )
    def update_panel_style(visible, width_val, height_val, _cid=_i):
        is_visible = _cid in (visible or [])
        if width_val == "full":
            basis = "calc(100% - 0px)"
        elif width_val == "quarter":
            basis = "calc(25% - 8px)"
        else:
            basis = "calc(50% - 5px)"
        return {
            "backgroundColor": PANEL_BG, "borderRadius": "8px",
            "border": f"1px solid {BORDER_COLOR}", "padding": "8px",
            "display": "flex" if is_visible else "none",
            "flexDirection": "column",
            "flexBasis": basis, "flexGrow": "0", "flexShrink": "0",
            "minWidth": "280px",
            "boxSizing": "border-box",
        }

    @app.callback(
        Output({"type": "graph", "index": _i}, "style"),
        Input({"type": "height-select", "index": _i}, "value"),
    )
    def update_graph_height(height_val, _cid=_i):
        try:
            h = int(height_val) if height_val else DEFAULT_HEIGHT_PX
        except (ValueError, TypeError):
            h = DEFAULT_HEIGHT_PX
        h = max(100, min(2000, h))
        return {"height": f"{h}px"}


# ---------------------------------------------------------------------------
# Callback: Toggle setup area visibility (Issue #15)
# ---------------------------------------------------------------------------

for _st in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "setup-area", "index": _st}, "style"),
        Output({"type": "setup-toggle", "index": _st}, "children"),
        Input({"type": "setup-toggle", "index": _st}, "n_clicks"),
        State({"type": "setup-area", "index": _st}, "style"),
        prevent_initial_call=True,
    )
    def toggle_setup_area(n_clicks, current_style, _cid=_st):
        if not n_clicks:
            return no_update, no_update
        is_hidden = (current_style or {}).get("display") == "none"
        new_style = {"display": "block" if is_hidden else "none"}
        label = "Setup \u25BC" if is_hidden else "Setup \u25B2"
        return new_style, label

    toggle_setup_area.__name__ = f"toggle_setup_area_{_st}"


# ---------------------------------------------------------------------------
# Callback: File upload
# ---------------------------------------------------------------------------

@app.callback(
    Output("sheet-select", "options"),
    Output("sheet-select", "value"),
    Output("temp-file-path", "data"),
    Output("file-name-display", "children"),
    Input("file-upload", "contents"),
    State("file-upload", "filename"),
    State("temp-file-path", "data"),
    prevent_initial_call=True,
)
def on_file_upload(contents, filename, old_temp_path):
    if contents is None:
        return no_update, no_update, no_update, no_update
    # Clean up previous temp file when a new file is uploaded (Issue #3)
    if old_temp_path:
        try:
            os.remove(old_temp_path)
        except OSError:
            pass
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    # Use NamedTemporaryFile pattern for safer temp file handling (Issue #3)
    tmp = tempfile.NamedTemporaryFile(
        prefix="wte_upload_", suffix=f"_{filename}", delete=False
    )
    temp_path = tmp.name
    try:
        tmp.write(decoded)
        tmp.close()
        xl = pd.ExcelFile(temp_path, engine="openpyxl")
        sheets = xl.sheet_names
        xl.close()
    except Exception as e:
        # Clean up on error
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return [], None, None, f"Error: {e}"
    options = [{"label": s, "value": s} for s in sheets]
    return options, None, temp_path, filename


# ---------------------------------------------------------------------------
# Callback: Sheet selected → load data
# ---------------------------------------------------------------------------

_load_outputs = [
    Output("session-data", "data"),
    Output("data-stats", "children"),
    Output("pkg-select", "options"),
]
for _c in range(1, MAX_CHARTS + 1):
    for _s in range(1, NUM_SERIES + 1):
        _load_outputs.append(Output({"type": "series-dd", "chart": _c, "series": _s}, "options", allow_duplicate=True))
        _load_outputs.append(Output({"type": "series-dd", "chart": _c, "series": _s}, "value", allow_duplicate=True))
    _load_outputs.append(Output({"type": "start-time", "index": _c}, "data", allow_duplicate=True))
    _load_outputs.append(Output({"type": "goto-date", "index": _c}, "value", allow_duplicate=True))


@app.callback(
    _load_outputs,
    Input("sheet-select", "value"),
    State("temp-file-path", "data"),
    prevent_initial_call=True,
)
def on_sheet_selected(sheet_name, temp_path):
    if not sheet_name or not temp_path:
        return [no_update] * len(_load_outputs)
    try:
        df = load_sheet_data(temp_path, sheet_name)
        tag_map, chart_packages = try_load_tag_refs(temp_path)
    except Exception as e:
        results = [no_update, f"Error loading sheet: {e}"]
        results.extend([no_update] * (len(_load_outputs) - 2))
        return results

    if len(df) == 0 or "Time" not in df.columns:
        results = [no_update, "No timestamp data found in this sheet."]
        results.extend([no_update] * (len(_load_outputs) - 2))
        return results

    all_tags = [c for c in df.columns if c != "Time"]
    data_start = df["Time"].iloc[0]
    data_end = df["Time"].iloc[-1]

    name_to_code = {}
    for code, info in tag_map.items():
        name_to_code[info["name"]] = code

    # Issue #4: Store session data as JSON in dcc.Store instead of global state
    session_data = {
        "df_json": df.to_json(date_format="iso", orient="split"),
        "tag_map": tag_map,
        "chart_packages": chart_packages,
        "all_tags": all_tags,
        "name_to_code": name_to_code,
        "data_start": data_start.isoformat(),
        "data_end": data_end.isoformat(),
    }

    stats = (
        f"Start: {data_start.strftime('%Y-%m-%d %H:%M')}  |  "
        f"End: {data_end.strftime('%Y-%m-%d %H:%M')}  |  "
        f"Data points: {len(df):,}  |  "
        f"Tags: {len(all_tags)}"
    )

    tag_options = [{"label": tag_label(c, tag_map), "value": c} for c in all_tags]
    pkg_options = [{"label": "-- None --", "value": ""}]
    for pkg in chart_packages:
        names = [n for n in pkg["tags"] if n]
        pkg_options.append({
            "label": f"Pkg {pkg['num']}: {' / '.join(names)}",
            "value": pkg["num"],
        })

    results = [session_data, stats, pkg_options]
    start_iso = data_start.isoformat()
    date_str = data_start.strftime("%Y-%m-%d")
    for _c in range(1, MAX_CHARTS + 1):
        for _s in range(1, NUM_SERIES + 1):
            results.append(tag_options)
            results.append(None)
        results.append(start_iso)
        results.append(date_str)
    return results


# ---------------------------------------------------------------------------
# Figure builder
# ---------------------------------------------------------------------------


def _interpolate_at(df, column, timestamp):
    """Linearly interpolate a column value at the given timestamp."""
    if column not in df.columns or "Time" not in df.columns:
        return None
    sub = df[["Time", column]].dropna(subset=[column])
    if sub.empty:
        return None
    times = sub["Time"]
    ts = pd.Timestamp(timestamp)
    if ts <= times.iloc[0]:
        return float(sub[column].iloc[0])
    if ts >= times.iloc[-1]:
        return float(sub[column].iloc[-1])
    idx_after = times.searchsorted(ts)
    idx_before = idx_after - 1
    t0, t1 = times.iloc[idx_before], times.iloc[idx_after]
    v0, v1 = float(sub[column].iloc[idx_before]), float(sub[column].iloc[idx_after])
    if t1 == t0:
        return v0
    frac = (ts - t0).total_seconds() / (t1 - t0).total_seconds()
    return v0 + frac * (v1 - v0)


def _build_figure(df_slice, selected_tags, tag_map, x_revision=None,
                   nicknames=None, own_scale_flags=None, lock_scale_flags=None,
                   show_limits=False, cursor_ts=None):
    """Build a Plotly figure.  Tags that share the same effective unit are
    drawn on a single shared Y-axis so the chart stays readable even with
    up to 10 active series.  Series whose slot has ``own_scale_flags[idx]``
    set are forced onto their own independent axis even when the unit matches
    another series.  Series with ``lock_scale_flags[idx]`` set have their
    Y-axis locked (``fixedrange=True``) so it cannot be zoomed/panned."""
    from collections import OrderedDict

    fig = go.Figure()
    if df_slice is None or df_slice.empty:
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
            font=dict(family="Consolas, monospace", size=11, color=TEXT_COLOR),
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            annotations=[dict(text="Load data to begin", showarrow=False,
                              font=dict(size=14, color=MUTED_TEXT),
                              xref="paper", yref="paper", x=0.5, y=0.5)],
        )
        return fig

    if nicknames is None:
        nicknames = {}
    if own_scale_flags is None:
        own_scale_flags = [False] * len(selected_tags)
    if lock_scale_flags is None:
        lock_scale_flags = [False] * len(selected_tags)

    # --- Step 1: Gather info for every active series -----------------------
    active_series = []  # (slot_idx, tag_code, display_name, display_unit, color, info)
    for idx, tag_code in enumerate(selected_tags):
        if not tag_code or tag_code not in df_slice.columns:
            continue
        info = tag_map.get(tag_code, {})
        name = info.get("name", tag_code)
        units = info.get("units", "")
        tag_nn = nicknames.get(tag_code, {})
        nickname = tag_nn.get("nickname", "")
        unit_override = tag_nn.get("unit", "")
        display_name = nickname if nickname else name
        display_unit = unit_override if unit_override else units
        color = TRACE_COLORS[idx % len(TRACE_COLORS)]
        active_series.append((idx, tag_code, display_name, display_unit, color, info))

    if not active_series:
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
            font=dict(family="Consolas, monospace", size=11, color=TEXT_COLOR),
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            annotations=[dict(text="Select tags to display", showarrow=False,
                              font=dict(size=14, color=MUTED_TEXT),
                              xref="paper", yref="paper", x=0.5, y=0.5)],
        )
        return fig

    # --- Step 2: Group series by effective unit ----------------------------
    # Tags with the SAME non-empty unit share one Y-axis *unless* the user
    # has ticked "Own" for that series slot.
    # Tags with no unit, or with "Own" checked, each get their own axis.
    unit_groups = OrderedDict()
    for s in active_series:
        slot_idx = s[0]
        is_own = own_scale_flags[slot_idx] if slot_idx < len(own_scale_flags) else False
        if is_own or not s[3]:
            # Force own axis — unique key per series
            unit_key = f"_own_{s[1]}"
        else:
            unit_key = s[3]
        if unit_key not in unit_groups:
            unit_groups[unit_key] = []
        unit_groups[unit_key].append(s)

    # --- Step 3: Assign one Y-axis per unit group, alternating L/R ---------
    unit_to_axis = {}
    active_axes = []
    for axis_idx, (unit_key, members) in enumerate(unit_groups.items()):
        axis_num = axis_idx + 1
        # Alternate left / right, stacking outward
        if axis_idx % 2 == 0:
            side, offset = "left", (axis_idx // 2) * 0.05
        else:
            side, offset = "right", (axis_idx // 2) * 0.05

        # Axis colour: use trace colour when solo, neutral when shared
        axis_color = members[0][4] if len(members) == 1 else TEXT_COLOR

        # Build axis label with series indicators
        display_unit = members[0][3]
        series_tags = ", ".join(f"S{m[0] + 1}" for m in members)
        if len(members) == 1:
            name_part = members[0][2]
            if display_unit:
                label = f"{name_part} [{display_unit}]"
            else:
                label = name_part
        else:
            # Shared axis: show which series share it
            if display_unit:
                label = f"{series_tags} [{display_unit}]"
            else:
                label = series_tags

        # Y-range: union of all members' y_high/y_low
        y_hi_vals = [m[5].get("y_high") for m in members if m[5].get("y_high") is not None]
        y_lo_vals = [m[5].get("y_low") for m in members if m[5].get("y_low") is not None]
        y_range = [min(y_lo_vals), max(y_hi_vals)] if y_hi_vals and y_lo_vals else None

        # Check if any member in this group has its scale locked
        is_locked = any(
            lock_scale_flags[m[0]] if m[0] < len(lock_scale_flags) else False
            for m in members
        )

        unit_to_axis[unit_key] = axis_num
        active_axes.append({
            "num": axis_num, "side": side, "offset": offset,
            "color": axis_color, "range": y_range, "label": label,
            "unit_key": unit_key, "locked": is_locked,
        })

    # --- Step 4: Add traces, each referencing its shared axis --------------
    for (idx, tag_code, display_name, display_unit, color, info) in active_series:
        is_own = own_scale_flags[idx] if idx < len(own_scale_flags) else False
        if is_own or not display_unit:
            unit_key = f"_own_{tag_code}"
        else:
            unit_key = display_unit
        axis_num = unit_to_axis[unit_key]
        yaxis_key = "y" if axis_num == 1 else f"y{axis_num}"
        trace_label = f"{display_name} [{display_unit}]" if display_unit else display_name
        fig.add_trace(go.Scattergl(
            x=df_slice["Time"], y=df_slice[tag_code],
            name=trace_label, yaxis=yaxis_key,
            line=dict(color=color, width=1.5), mode="lines",
        ))

    # --- Step 4b: Add threshold limit lines (Issue #11) --------------------
    limit_shapes = []
    limit_annotations = []
    if show_limits:
        for (idx, tag_code, display_name, display_unit, color, info) in active_series:
            y_high = info.get("y_high")
            y_low = info.get("y_low")
            if y_high is None and y_low is None:
                continue
            is_own = own_scale_flags[idx] if idx < len(own_scale_flags) else False
            if is_own or not display_unit:
                unit_key = f"_own_{tag_code}"
            else:
                unit_key = display_unit
            axis_num = unit_to_axis[unit_key]
            yref = "y" if axis_num == 1 else f"y{axis_num}"

            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            line_color = f"rgba({r},{g},{b},0.45)"

            for val, label_suffix in [(y_high, "Hi"), (y_low, "Lo")]:
                if val is None:
                    continue
                limit_shapes.append(dict(
                    type="line", xref="paper", x0=0, x1=1,
                    yref=yref, y0=val, y1=val,
                    line=dict(color=line_color, width=1.2, dash="dash"),
                    layer="above",
                ))
                limit_annotations.append(dict(
                    text=f"S{idx+1} {label_suffix}: {val}",
                    xref="paper", x=1.0, yref=yref, y=val,
                    xanchor="left", showarrow=False,
                    font=dict(size=9, color=line_color),
                    bgcolor="rgba(13,17,23,0.7)",
                ))

    # --- Step 4c: Add cursor vertical line (Issue #9) ----------------------
    if cursor_ts:
        try:
            ct = pd.Timestamp(cursor_ts)
            limit_shapes.append(dict(
                type="line", yref="paper", y0=0, y1=1,
                xref="x", x0=ct, x1=ct,
                line=dict(color="#d2a8ff", width=1.5, dash="dashdot"),
                layer="above",
            ))
        except Exception:
            pass

    # --- Step 5: Build Y-axis layout dicts ---------------------------------
    max_left = max((a["offset"] for a in active_axes if a["side"] == "left"), default=0)
    max_right = max((a["offset"] for a in active_axes if a["side"] == "right"), default=0)
    x_domain = [max_left, 1.0 - max_right]

    yaxis_layouts = {}
    for ax in active_axes:
        key = "yaxis" if ax["num"] == 1 else f"yaxis{ax['num']}"
        if ax["side"] == "left":
            position = max_left - ax["offset"]
        else:
            position = (1.0 - max_right) + ax["offset"]
        layout = dict(
            title=dict(text=ax["label"], font=dict(color=ax["color"], size=10)),
            tickfont=dict(color=ax["color"], size=9),
            gridcolor=GRID_COLOR if ax["num"] == 1 else "rgba(0,0,0,0)",
            showgrid=(ax["num"] == 1), zeroline=False, side=ax["side"],
            uirevision=ax["unit_key"],
            fixedrange=ax.get("locked", False),
        )
        if ax["range"]:
            layout["range"] = ax["range"]
        if ax["num"] > 1:
            layout["overlaying"] = "y"
            layout["position"] = position
            layout["anchor"] = "free"
        yaxis_layouts[key] = layout

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(family="Consolas, monospace", size=11, color=TEXT_COLOR),
        margin=dict(l=45 if max_left > 0 else 10,
                    r=45 if max_right > 0 else 10, t=10, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=10)),
        xaxis=dict(gridcolor=GRID_COLOR, showgrid=True, zeroline=False,
                   tickformat="%H:%M\n%d-%b", domain=x_domain,
                   uirevision=x_revision),
        uirevision="keep",
        hovermode="x unified",
        shapes=limit_shapes,
        annotations=limit_annotations,
        **yaxis_layouts,
    )
    return fig


# ---------------------------------------------------------------------------
# Chart update callbacks — one per pre-allocated chart slot
# ---------------------------------------------------------------------------

for _ci in range(1, MAX_CHARTS + 1):
    _series_inputs = [
        Input({"type": "series-dd", "chart": _ci, "series": s}, "value")
        for s in range(1, NUM_SERIES + 1)
    ]
    _own_scale_inputs = [
        Input({"type": "own-scale", "chart": _ci, "series": s}, "value")
        for s in range(1, NUM_SERIES + 1)
    ]
    _lock_scale_inputs = [
        Input({"type": "lock-scale", "chart": _ci, "series": s}, "value")
        for s in range(1, NUM_SERIES + 1)
    ]
    _filter_inputs = [
        Input({"type": "filter-window", "chart": _ci, "series": s}, "value")
        for s in range(1, NUM_SERIES + 1)
    ]

    @app.callback(
        Output({"type": "graph", "index": _ci}, "figure"),
        Output({"type": "start-time", "index": _ci}, "data", allow_duplicate=True),
        Output({"type": "goto-date", "index": _ci}, "value", allow_duplicate=True),
        Output({"type": "goto-time", "index": _ci}, "value", allow_duplicate=True),
        *_series_inputs,
        *_own_scale_inputs,
        *_lock_scale_inputs,
        *_filter_inputs,
        Input({"type": "goto-date", "index": _ci}, "value"),
        Input({"type": "goto-time", "index": _ci}, "value"),
        Input({"type": "win-min", "index": _ci}, "value"),
        Input({"type": "win-hr", "index": _ci}, "value"),
        Input({"type": "step", "index": _ci}, "value"),
        Input({"type": "scroll-left", "index": _ci}, "n_clicks"),
        Input({"type": "scroll-right", "index": _ci}, "n_clicks"),
        Input("tag-nicknames", "data"),
        Input({"type": "show-limits", "index": _ci}, "value"),
        Input({"type": "cursor-ts", "index": _ci}, "data"),
        State({"type": "start-time", "index": _ci}, "data"),
        State("session-data", "data"),
        prevent_initial_call=True,
    )
    def update_chart(*args, _cid=_ci):
        tags = list(args[:NUM_SERIES])
        own_checklists = list(args[NUM_SERIES:NUM_SERIES * 2])
        own_flags = [("own" in (v or [])) for v in own_checklists]
        lock_checklists = list(args[NUM_SERIES * 2:NUM_SERIES * 3])
        lock_flags = [("lock" in (v or [])) for v in lock_checklists]
        filter_windows = list(args[NUM_SERIES * 3:NUM_SERIES * 4])
        rest = args[NUM_SERIES * 4:]
        goto_date, goto_time, win_min, win_hr, step, n_left, n_right, nn_data, show_limits_val, cursor_ts_val, start_time_iso, session_data = rest
        show_limits = "limits" in (show_limits_val or [])

        # Issue #4: Read from per-session store instead of global state
        if not session_data:
            return _build_figure(None, [], {}), no_update, no_update, no_update

        df = pd.read_json(StringIO(session_data["df_json"]), orient="split")
        if "Time" in df.columns:
            df["Time"] = pd.to_datetime(df["Time"])
        tag_map = session_data["tag_map"]
        data_start = pd.Timestamp(session_data["data_start"])
        data_end = pd.Timestamp(session_data["data_end"])

        if df.empty or data_start is None:
            return _build_figure(None, [], {}), no_update, no_update, no_update

        ctx = callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        start_time = pd.Timestamp(start_time_iso) if start_time_iso else data_start

        if "goto-date" in triggered or "goto-time" in triggered:
            try:
                d = goto_date or data_start.strftime("%Y-%m-%d")
                t = goto_time or "00:00"
                start_time = pd.Timestamp(f"{d} {t}")
            except (ValueError, TypeError):
                pass

        w_min = (win_min or 0) + (win_hr or 0) * 60
        if w_min <= 0:
            w_min = 60
        step_min = step if step and step > 0 else 5

        if "scroll-left" in triggered:
            start_time = start_time - timedelta(minutes=step_min)
        elif "scroll-right" in triggered:
            start_time = start_time + timedelta(minutes=step_min)

        if start_time < data_start:
            start_time = data_start
        end_time = start_time + timedelta(minutes=w_min)
        if end_time > data_end:
            end_time = data_end
            start_time = max(data_start, end_time - timedelta(minutes=w_min))

        mask = (df["Time"] >= start_time) & (df["Time"] <= end_time)
        df_slice = df.loc[mask].copy()

        # Apply rolling mean filter per series (Issue #18)
        for idx, tag_code in enumerate(tags):
            if not tag_code or tag_code not in df_slice.columns:
                continue
            fw = filter_windows[idx]
            try:
                fw = int(fw) if fw else 1
            except (ValueError, TypeError):
                fw = 1
            if fw > 1:
                df_slice[tag_code] = (
                    df_slice[tag_code]
                    .rolling(window=fw, min_periods=1, center=True)
                    .mean()
                )

        fig = _build_figure(df_slice, tags, tag_map,
                            x_revision=start_time.isoformat(),
                            nicknames=nn_data or {},
                            own_scale_flags=own_flags,
                            lock_scale_flags=lock_flags,
                            show_limits=show_limits,
                            cursor_ts=cursor_ts_val)
        return fig, start_time.isoformat(), start_time.strftime("%Y-%m-%d"), start_time.strftime("%H:%M")

    update_chart.__name__ = f"update_chart_{_ci}"


# ---------------------------------------------------------------------------
# Sync callbacks
# ---------------------------------------------------------------------------

# --- Toggle sync state when any sync button is clicked ---
@app.callback(
    Output("sync-state", "data", allow_duplicate=True),
    [Input({"type": "sync-btn", "index": i}, "n_clicks") for i in range(1, MAX_CHARTS + 1)],
    State("sync-state", "data"),
    prevent_initial_call=True,
)
def toggle_sync(*args):
    clicks = args[:MAX_CHARTS]
    sync_state = args[MAX_CHARTS]
    ctx = callback_context
    if not ctx.triggered:
        return no_update
    triggered = ctx.triggered[0]["prop_id"]
    try:
        prop = json.loads(triggered.rsplit(".", 1)[0])
        chart_id = prop["index"]
    except Exception:
        return no_update

    if sync_state and sync_state.get("active"):
        # Only the master can deactivate sync; locked charts do nothing
        if sync_state.get("master") == chart_id:
            return {"active": False, "master": None}
        return no_update
    else:
        # Activate sync with this chart as master
        return {"active": True, "master": chart_id}


# --- Propagate master time settings to all other charts when sync activates
#     or when master's time controls change ---
for _si in range(1, MAX_CHARTS + 1):
    # Build outputs for all OTHER charts (non-master candidates)
    _sync_outputs = []
    _sync_output_charts = []
    for _oi in range(1, MAX_CHARTS + 1):
        if _oi == _si:
            continue
        _sync_outputs.extend([
            Output({"type": "start-time", "index": _oi}, "data", allow_duplicate=True),
            Output({"type": "goto-date", "index": _oi}, "value", allow_duplicate=True),
            Output({"type": "goto-time", "index": _oi}, "value", allow_duplicate=True),
            Output({"type": "win-min", "index": _oi}, "value", allow_duplicate=True),
            Output({"type": "win-hr", "index": _oi}, "value", allow_duplicate=True),
            Output({"type": "step", "index": _oi}, "value", allow_duplicate=True),
        ])
        _sync_output_charts.append(_oi)

    @app.callback(
        _sync_outputs,
        Input("sync-state", "data"),
        Input({"type": "start-time", "index": _si}, "data"),
        Input("visible-charts", "data"),
        State({"type": "goto-date", "index": _si}, "value"),
        State({"type": "goto-time", "index": _si}, "value"),
        State({"type": "win-min", "index": _si}, "value"),
        State({"type": "win-hr", "index": _si}, "value"),
        State({"type": "step", "index": _si}, "value"),
        prevent_initial_call=True,
    )
    def propagate_sync(sync_state, start_iso, visible, goto_date, goto_time,
                       win_min, win_hr, step, _master=_si,
                       _targets=list(_sync_output_charts)):
        n_targets = len(_targets)
        n_outputs = n_targets * 6
        if not sync_state or not sync_state.get("active"):
            return [no_update] * n_outputs
        if sync_state.get("master") != _master:
            return [no_update] * n_outputs
        # Propagate master settings to all other visible charts
        results = []
        for t in _targets:
            if t in (visible or []):
                results.extend([
                    start_iso,
                    goto_date,
                    goto_time,
                    win_min,
                    win_hr,
                    step,
                ])
            else:
                results.extend([no_update] * 6)
        return results

    propagate_sync.__name__ = f"propagate_sync_{_si}"


# --- Visual indicator: update panel style based on sync state ---
# Overrides the existing panel style callback with sync awareness
for _vi in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "chart-wrapper", "index": _vi}, "style", allow_duplicate=True),
        Input("sync-state", "data"),
        State("visible-charts", "data"),
        State({"type": "width-select", "index": _vi}, "value"),
        prevent_initial_call=True,
    )
    def update_sync_border(sync_state, visible, width_val, _cid=_vi):
        is_visible = _cid in (visible or [])
        if width_val == "full":
            basis = "calc(100% - 0px)"
        elif width_val == "quarter":
            basis = "calc(25% - 8px)"
        else:
            basis = "calc(50% - 5px)"
        is_master = (sync_state and sync_state.get("active")
                     and sync_state.get("master") == _cid)
        border = "2px solid #00e5ff" if is_master else f"1px solid {BORDER_COLOR}"
        return {
            "backgroundColor": PANEL_BG, "borderRadius": "8px",
            "border": border, "padding": "8px",
            "display": "flex" if is_visible else "none",
            "flexDirection": "column",
            "flexBasis": basis, "flexGrow": "0", "flexShrink": "0",
            "minWidth": "280px",
            "boxSizing": "border-box",
        }

    update_sync_border.__name__ = f"update_sync_border_{_vi}"


# --- Update sync button label based on sync state ---
for _bi in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "sync-btn", "index": _bi}, "children"),
        Output({"type": "sync-btn", "index": _bi}, "style"),
        Input("sync-state", "data"),
        prevent_initial_call=True,
    )
    def update_sync_btn(sync_state, _cid=_bi):
        if sync_state and sync_state.get("active"):
            if sync_state.get("master") == _cid:
                # Master: show Unsync button with highlight
                return ("\U0001F517 Unsync", {
                    **BTN_STYLE, "color": "#0d1117",
                    "backgroundColor": "#00e5ff",
                    "fontSize": "11px", "padding": "2px 10px",
                    "fontWeight": "bold",
                })
            else:
                # Locked: dimmed sync button
                return ("\U0001F512 Locked", {
                    **BTN_STYLE, "color": MUTED_TEXT,
                    "fontSize": "11px", "padding": "2px 10px",
                    "cursor": "default", "opacity": "0.6",
                })
        # Not synced: normal sync button
        return ("\U0001F517 Sync", {
            **BTN_STYLE, "color": "#58a6ff",
            "fontSize": "11px", "padding": "2px 10px",
        })

    update_sync_btn.__name__ = f"update_sync_btn_{_bi}"


# --- Disable / enable time controls based on sync state ---
for _di in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "goto-date", "index": _di}, "disabled"),
        Output({"type": "goto-time", "index": _di}, "disabled"),
        Output({"type": "win-min", "index": _di}, "disabled"),
        Output({"type": "win-hr", "index": _di}, "disabled"),
        Output({"type": "step", "index": _di}, "disabled"),
        Output({"type": "scroll-left", "index": _di}, "disabled"),
        Output({"type": "scroll-right", "index": _di}, "disabled"),
        Output({"type": "load-area-btn", "index": _di}, "disabled"),
        Input("sync-state", "data"),
        prevent_initial_call=True,
    )
    def toggle_controls(sync_state, _cid=_di):
        if sync_state and sync_state.get("active"):
            if sync_state.get("master") == _cid:
                # Master: controls remain enabled
                return False, False, False, False, False, False, False, False
            else:
                # Locked: disable all time controls
                return True, True, True, True, True, True, True, True
        # Not synced: all enabled
        return False, False, False, False, False, False, False, False

    toggle_controls.__name__ = f"toggle_controls_{_di}"


# ---------------------------------------------------------------------------
# Sync zoom: propagate master chart X-axis zoom/pan to all synced charts
# ---------------------------------------------------------------------------

# Build outputs: for each chart, update start-time, goto-date, goto-time, win-min, win-hr
_zoom_sync_outputs = []
for _zi in range(1, MAX_CHARTS + 1):
    _zoom_sync_outputs.extend([
        Output({"type": "start-time", "index": _zi}, "data", allow_duplicate=True),
        Output({"type": "goto-date", "index": _zi}, "value", allow_duplicate=True),
        Output({"type": "goto-time", "index": _zi}, "value", allow_duplicate=True),
        Output({"type": "win-min", "index": _zi}, "value", allow_duplicate=True),
        Output({"type": "win-hr", "index": _zi}, "value", allow_duplicate=True),
    ])


@app.callback(
    _zoom_sync_outputs,
    [Input({"type": "graph", "index": i}, "relayoutData") for i in range(1, MAX_CHARTS + 1)],
    State("sync-state", "data"),
    State("visible-charts", "data"),
    prevent_initial_call=True,
)
def sync_zoom_from_master(*args):
    """When the master chart is zoomed/panned on the X-axis, propagate the
    new time range to all synced charts (including the master itself so its
    controls stay consistent)."""
    n_total = MAX_CHARTS * 5
    relayout_list = args[:MAX_CHARTS]
    sync_state = args[MAX_CHARTS]
    visible = args[MAX_CHARTS + 1]

    if not sync_state or not sync_state.get("active"):
        return [no_update] * n_total

    master = sync_state.get("master")
    if master is None:
        return [no_update] * n_total

    ctx = callback_context
    if not ctx.triggered:
        return [no_update] * n_total

    # Identify which graph triggered the callback
    triggered = ctx.triggered[0]["prop_id"]
    try:
        prop = json.loads(triggered.rsplit(".", 1)[0])
        triggered_chart = prop["index"]
    except Exception:
        return [no_update] * n_total

    # Only react when the master chart fires the relayoutData
    if triggered_chart != master:
        return [no_update] * n_total

    # Get the master's relayoutData
    relayout = relayout_list[master - 1]  # 1-indexed → 0-indexed
    if not relayout:
        return [no_update] * n_total

    x0 = relayout.get("xaxis.range[0]")
    x1 = relayout.get("xaxis.range[1]")

    if x0 is None or x1 is None:
        return [no_update] * n_total

    # Parse the range timestamps
    try:
        t0 = pd.Timestamp(x0)
        t1 = pd.Timestamp(x1)
    except Exception:
        return [no_update] * n_total

    if t1 <= t0:
        return [no_update] * n_total

    # Calculate window duration in minutes
    delta = t1 - t0
    total_minutes = delta.total_seconds() / 60.0
    win_hr = int(total_minutes // 60)
    win_min = round(total_minutes - win_hr * 60)

    # Ensure at least 1 minute window
    if win_hr == 0 and win_min == 0:
        win_min = 1

    start_iso = t0.isoformat()
    date_str = t0.strftime("%Y-%m-%d")
    time_str = t0.strftime("%H:%M")

    # Build results: update all visible synced charts (including master)
    results = []
    for ci in range(1, MAX_CHARTS + 1):
        if ci in (visible or []):
            results.extend([start_iso, date_str, time_str, win_min, win_hr])
        else:
            results.extend([no_update] * 5)
    return results


# ---------------------------------------------------------------------------
# Tag Manager: toggle panel visibility
# ---------------------------------------------------------------------------

@app.callback(
    Output("tag-panel", "style"),
    Output("tag-panel-toggle", "children"),
    Input("tag-panel-toggle", "n_clicks"),
    State("tag-panel", "style"),
    prevent_initial_call=True,
)
def toggle_tag_panel(n_clicks, current_style):
    if not n_clicks:
        return no_update, no_update
    is_hidden = current_style.get("display") == "none"
    new_style = {**current_style, "display": "block" if is_hidden else "none"}
    label = "Tag Manager \u25B2" if is_hidden else "Tag Manager \u25BC"
    return new_style, label


# ---------------------------------------------------------------------------
# Notes overlay: toggle, load, and save (Issue #12)
# ---------------------------------------------------------------------------

@app.callback(
    Output("notes-overlay", "style"),
    Input("notes-toggle-btn", "n_clicks"),
    Input("notes-close-btn", "n_clicks"),
    State("notes-overlay", "style"),
    prevent_initial_call=True,
)
def toggle_notes(toggle_clicks, close_clicks, current_style):
    ctx = callback_context
    if not ctx.triggered:
        return no_update
    is_hidden = (current_style or {}).get("display") == "none"
    if "notes-close-btn" in ctx.triggered[0]["prop_id"]:
        return {**current_style, "display": "none"}
    return {**current_style, "display": "flex" if is_hidden else "none"}


@app.callback(
    Output("notes-textarea", "value"),
    Input("notes-text", "data"),
)
def load_notes(saved_text):
    """Initialise the textarea from localStorage on page load."""
    return saved_text or ""


@app.callback(
    Output("notes-text", "data"),
    Input("notes-textarea", "value"),
    prevent_initial_call=True,
)
def save_notes(text):
    """Persist textarea content to localStorage."""
    return text or ""


# ---------------------------------------------------------------------------
# Tag Manager: populate tag rows when data is loaded
# ---------------------------------------------------------------------------

UNIT_OPTIONS = [
    {"label": u, "value": u}
    for u in ["", "m\u00b3/hr", "%", "t/hr", "mbar", "\u00b0C", "MW", "bar", "kg/s", "RPM", "mm", "l/hr"]
]

# Set of built-in unit values for duplicate checking
_BUILTIN_UNITS = {opt["value"] for opt in UNIT_OPTIONS}


@app.callback(
    Output("custom-units", "data"),
    Output("custom-unit-input", "value"),
    Input("add-unit-btn", "n_clicks"),
    State("custom-unit-input", "value"),
    State("custom-units", "data"),
    prevent_initial_call=True,
)
def add_custom_unit(n_clicks, new_unit, custom_units):
    """Add a user-defined unit to the custom-units store."""
    if not n_clicks:
        return no_update, no_update
    if custom_units is None:
        custom_units = []
    if not new_unit or not new_unit.strip():
        return no_update, no_update
    unit = new_unit.strip()
    if unit in _BUILTIN_UNITS or unit in custom_units:
        # Already exists -- just clear the input
        return no_update, ""
    custom_units = custom_units + [unit]

    # Persist to local JSON file
    nicknames, _ = _load_tag_manager_data()
    _save_tag_manager_data(nicknames, custom_units)

    return custom_units, ""


@app.callback(
    Output("tag-rows-container", "children"),
    Input("data-stats", "children"),
    Input("custom-units", "data"),
    State("tag-nicknames", "data"),
    State("session-data", "data"),
)
def populate_tag_rows(stats_text, custom_units, saved_nicknames, session_data):
    """Rebuild the tag table rows whenever new data is loaded or custom units change."""
    if not session_data:
        return html.Span("No tags loaded.", style={"color": MUTED_TEXT, "fontSize": "12px"})
    tag_map = session_data.get("tag_map", {})
    all_tags = session_data.get("all_tags", [])
    if not all_tags:
        return html.Span("No tags loaded.", style={"color": MUTED_TEXT, "fontSize": "12px"})

    if saved_nicknames is None:
        saved_nicknames = {}

    # Combine built-in units with any user-added custom units
    if custom_units:
        all_unit_options = UNIT_OPTIONS + [
            {"label": u, "value": u} for u in custom_units
        ]
    else:
        all_unit_options = UNIT_OPTIONS

    rows = []
    for tag_code in all_tags:
        info = tag_map.get(tag_code, {})
        current_name = info.get("name", tag_code)
        default_unit = info.get("units", "")

        # Retrieve saved nickname/unit if any
        saved = saved_nicknames.get(tag_code, {})
        saved_nick = saved.get("nickname", "")
        saved_unit = saved.get("unit", default_unit)

        row = html.Div(style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1.5fr 1fr 1fr",
            "gap": "6px",
            "padding": "3px 0",
            "alignItems": "center",
            "borderBottom": f"1px solid {GRID_COLOR}",
        }, children=[
            html.Span(tag_code, style={
                "color": TEXT_COLOR, "fontSize": "11px",
                "overflow": "hidden", "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            }, title=tag_code),
            html.Span(current_name, style={
                "color": MUTED_TEXT, "fontSize": "11px",
                "overflow": "hidden", "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            }, title=current_name),
            dcc.Input(
                id={"type": "tag-nickname", "tag": tag_code},
                type="text", value=saved_nick,
                placeholder="Nickname...",
                style={**INPUT_STYLE, "width": "100%", "fontSize": "11px"},
                debounce=True,
            ),
            dcc.Dropdown(
                id={"type": "tag-unit", "tag": tag_code},
                options=all_unit_options,
                value=saved_unit,
                placeholder="Unit...",
                clearable=True,
                style={**DROPDOWN_STYLE, "width": "100%", "fontSize": "11px"},
                className="dark-dropdown",
            ),
        ])
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Tag Manager: store nicknames/units when any input changes
# ---------------------------------------------------------------------------

@app.callback(
    Output("tag-nicknames", "data"),
    Input({"type": "tag-nickname", "tag": ALL}, "value"),
    Input({"type": "tag-unit", "tag": ALL}, "value"),
    State("tag-nicknames", "data"),
    prevent_initial_call=True,
)
def update_tag_nicknames(nicknames, units, current_data):
    """Persist nickname and unit edits into the session store and JSON file."""
    ctx = callback_context
    if not ctx.triggered:
        return no_update

    if current_data is None:
        current_data = {}

    # Process all inputs via their pattern-matching IDs
    nick_inputs = ctx.inputs_list[0] if ctx.inputs_list else []
    unit_inputs = ctx.inputs_list[1] if len(ctx.inputs_list) > 1 else []

    for inp in nick_inputs:
        tag_code = inp["id"]["tag"]
        val = inp.get("value", "")
        if tag_code not in current_data:
            current_data[tag_code] = {}
        current_data[tag_code]["nickname"] = val or ""

    for inp in unit_inputs:
        tag_code = inp["id"]["tag"]
        val = inp.get("value", "")
        if tag_code not in current_data:
            current_data[tag_code] = {}
        current_data[tag_code]["unit"] = val or ""

    # Persist to local JSON file
    _, custom_units = _load_tag_manager_data()
    _save_tag_manager_data(current_data, custom_units)

    return current_data


# ---------------------------------------------------------------------------
# Update series dropdown labels when nicknames/units change (Issue #14)
# ---------------------------------------------------------------------------

_nickname_dd_outputs = []
for _c in range(1, MAX_CHARTS + 1):
    for _s in range(1, NUM_SERIES + 1):
        _nickname_dd_outputs.append(
            Output({"type": "series-dd", "chart": _c, "series": _s}, "options", allow_duplicate=True)
        )


@app.callback(
    _nickname_dd_outputs,
    Input("tag-nicknames", "data"),
    State("session-data", "data"),
    prevent_initial_call=True,
)
def update_dropdown_labels(nn_data, session_data):
    """Rebuild series dropdown options when tag nicknames or units change."""
    if not session_data:
        return [no_update] * len(_nickname_dd_outputs)
    tag_map = session_data.get("tag_map", {})
    all_tags = session_data.get("all_tags", [])
    if not all_tags:
        return [no_update] * len(_nickname_dd_outputs)

    if nn_data is None:
        nn_data = {}

    # Build updated options incorporating nickname/unit overrides
    tag_options = []
    for c in all_tags:
        info = tag_map.get(c, {})
        nn = nn_data.get(c, {})
        nickname = nn.get("nickname", "")
        unit_override = nn.get("unit", "")

        name = nickname if nickname else info.get("name", c)
        units = unit_override if unit_override else info.get("units", "")
        unit_str = f" [{units}]" if units else ""
        label = f"{c} - {name}{unit_str}"
        tag_options.append({"label": label, "value": c})

    # Return same updated options list for every series dropdown
    return [tag_options] * len(_nickname_dd_outputs)


# ---------------------------------------------------------------------------
# Chart Package callback — loads into chart 1
# ---------------------------------------------------------------------------

_pkg_outputs = [
    Output({"type": "series-dd", "chart": 1, "series": s}, "value", allow_duplicate=True)
    for s in range(1, NUM_SERIES + 1)
]

@app.callback(
    _pkg_outputs,
    Input("pkg-select", "value"),
    State("session-data", "data"),
    prevent_initial_call=True,
)
def load_chart_package(pkg_num, session_data):
    if not pkg_num:
        return [no_update] * NUM_SERIES
    # Issue #4: Read from per-session store instead of global state
    if not session_data:
        return [no_update] * NUM_SERIES
    name_to_code = session_data["name_to_code"]
    all_tags = session_data["all_tags"]
    for pkg in session_data["chart_packages"]:
        if pkg["num"] == pkg_num:
            codes = []
            for n in pkg["tags"]:
                if not n:
                    codes.append(None)
                elif n in name_to_code:
                    codes.append(name_to_code[n])
                elif n in all_tags:
                    codes.append(n)
                else:
                    codes.append(None)
            while len(codes) < NUM_SERIES:
                codes.append(None)
            return codes[:NUM_SERIES]
    return [no_update] * NUM_SERIES


# ---------------------------------------------------------------------------
# Save Setup callback — save current config to localStorage
# ---------------------------------------------------------------------------

# Gather all State inputs needed to capture current chart configuration
_save_states = []
for _c in range(1, MAX_CHARTS + 1):
    for _s in range(1, NUM_SERIES + 1):
        _save_states.append(State({"type": "series-dd", "chart": _c, "series": _s}, "value"))
    for _s in range(1, NUM_SERIES + 1):
        _save_states.append(State({"type": "own-scale", "chart": _c, "series": _s}, "value"))
    for _s in range(1, NUM_SERIES + 1):
        _save_states.append(State({"type": "lock-scale", "chart": _c, "series": _s}, "value"))
    for _s in range(1, NUM_SERIES + 1):
        _save_states.append(State({"type": "filter-window", "chart": _c, "series": _s}, "value"))
    _save_states.append(State({"type": "width-select", "index": _c}, "value"))
    _save_states.append(State({"type": "height-select", "index": _c}, "value"))
    _save_states.append(State({"type": "start-time", "index": _c}, "data"))
    _save_states.append(State({"type": "goto-date", "index": _c}, "value"))
    _save_states.append(State({"type": "goto-time", "index": _c}, "value"))
    _save_states.append(State({"type": "win-min", "index": _c}, "value"))
    _save_states.append(State({"type": "win-hr", "index": _c}, "value"))
    _save_states.append(State({"type": "step", "index": _c}, "value"))


@app.callback(
    Output("saved-setups", "data", allow_duplicate=True),
    Output("setup-status-msg", "children", allow_duplicate=True),
    Output("setup-name-input", "value"),
    Input("save-setup-btn", "n_clicks"),
    State("setup-name-input", "value"),
    State("saved-setups", "data"),
    State("visible-charts", "data"),
    State("file-name-display", "children"),
    State("sheet-select", "value"),
    State("sync-state", "data"),
    *_save_states,
    prevent_initial_call=True,
)
def save_setup(n_clicks, setup_name, saved, visible, file_name, sheet_name, sync_state, *chart_args):
    if not n_clicks:
        return no_update, no_update, no_update
    if not setup_name or not setup_name.strip():
        return no_update, "Enter a name first.", no_update

    setup_name = setup_name.strip()
    if saved is None:
        saved = {}

    # Parse chart_args: series + own-scale + lock-scale + filter-window + width + height + time settings per chart
    per_chart = NUM_SERIES * 4 + 8
    charts_config = {}
    for c in range(MAX_CHARTS):
        offset = c * per_chart
        series_vals = list(chart_args[offset:offset + NUM_SERIES])
        own_vals = list(chart_args[offset + NUM_SERIES:offset + NUM_SERIES * 2])
        lock_vals = list(chart_args[offset + NUM_SERIES * 2:offset + NUM_SERIES * 3])
        filter_vals = list(chart_args[offset + NUM_SERIES * 3:offset + NUM_SERIES * 4])
        width_val = chart_args[offset + NUM_SERIES * 4]
        height_val = chart_args[offset + NUM_SERIES * 4 + 1]
        start_time_val = chart_args[offset + NUM_SERIES * 4 + 2]
        goto_date_val = chart_args[offset + NUM_SERIES * 4 + 3]
        goto_time_val = chart_args[offset + NUM_SERIES * 4 + 4]
        win_min_val = chart_args[offset + NUM_SERIES * 4 + 5]
        win_hr_val = chart_args[offset + NUM_SERIES * 4 + 6]
        step_val = chart_args[offset + NUM_SERIES * 4 + 7]
        charts_config[str(c + 1)] = {
            "series": series_vals,
            "own_scale": own_vals,
            "lock_scale": lock_vals,
            "filter_window": filter_vals,
            "width": width_val,
            "height": height_val,
            "start_time": start_time_val,
            "goto_date": goto_date_val,
            "goto_time": goto_time_val,
            "win_min": win_min_val,
            "win_hr": win_hr_val,
            "step": step_val,
        }

    saved[setup_name] = {
        "visible": visible,
        "charts": charts_config,
        "file_name": file_name,
        "sheet_name": sheet_name,
        "sync_state": sync_state,
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return saved, f"Saved \"{setup_name}\" at {now}.", ""


# ---------------------------------------------------------------------------
# Update the load-setup dropdown options whenever saved-setups changes
# ---------------------------------------------------------------------------

@app.callback(
    Output("load-setup-dropdown", "options"),
    Input("saved-setups", "data"),
)
def update_setup_dropdown(saved):
    if not saved:
        return []
    options = []
    for name, cfg in saved.items():
        ref_file = cfg.get("file_name", "")
        ref_sheet = cfg.get("sheet_name", "")
        label = name
        if ref_file and ref_file != "No file loaded":
            label += f"  ({ref_file}"
            if ref_sheet:
                label += f" / {ref_sheet}"
            label += ")"
        options.append({"label": label, "value": name})
    return options


# ---------------------------------------------------------------------------
# Load Setup callback — restore chart config from localStorage
# ---------------------------------------------------------------------------

_load_setup_outputs = [
    Output("visible-charts", "data", allow_duplicate=True),
    Output("setup-status-msg", "children", allow_duplicate=True),
    Output("sync-state", "data", allow_duplicate=True),
]
for _c in range(1, MAX_CHARTS + 1):
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "series-dd", "chart": _c, "series": _s}, "value", allow_duplicate=True)
        )
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "own-scale", "chart": _c, "series": _s}, "value", allow_duplicate=True)
        )
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "lock-scale", "chart": _c, "series": _s}, "value", allow_duplicate=True)
        )
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "lock-scale-btn", "chart": _c, "series": _s}, "children", allow_duplicate=True)
        )
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "lock-scale-btn", "chart": _c, "series": _s}, "style", allow_duplicate=True)
        )
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "filter-window", "chart": _c, "series": _s}, "value", allow_duplicate=True)
        )
    _load_setup_outputs.append(
        Output({"type": "width-select", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "height-select", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "start-time", "index": _c}, "data", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "goto-date", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "goto-time", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "win-min", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "win-hr", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "step", "index": _c}, "value", allow_duplicate=True)
    )


@app.callback(
    _load_setup_outputs,
    Input("load-setup-dropdown", "value"),
    State("saved-setups", "data"),
    prevent_initial_call=True,
)
def load_setup(selected_name, saved):
    if not selected_name or not saved or selected_name not in saved:
        return [no_update] * len(_load_setup_outputs)

    cfg = saved[selected_name]
    visible = cfg.get("visible", list(range(1, INITIAL_VISIBLE + 1)))
    charts = cfg.get("charts", {})

    sync_state = cfg.get("sync_state", {"active": False, "master": None})
    results = [visible, f"Loaded \"{selected_name}\".", sync_state]

    for c in range(1, MAX_CHARTS + 1):
        chart_cfg = charts.get(str(c), {})
        series_vals = chart_cfg.get("series", [None] * NUM_SERIES)
        while len(series_vals) < NUM_SERIES:
            series_vals.append(None)
        for s_val in series_vals[:NUM_SERIES]:
            results.append(s_val)
        # Restore own-scale flags (backward-compatible: default to [] if missing)
        own_vals = chart_cfg.get("own_scale", [[] for _ in range(NUM_SERIES)])
        while len(own_vals) < NUM_SERIES:
            own_vals.append([])
        for ov in own_vals[:NUM_SERIES]:
            results.append(ov if ov else [])
        # Restore lock-scale flags (backward-compatible: default to [] if missing)
        lock_vals = chart_cfg.get("lock_scale", [[] for _ in range(NUM_SERIES)])
        while len(lock_vals) < NUM_SERIES:
            lock_vals.append([])
        for lv in lock_vals[:NUM_SERIES]:
            results.append(lv if lv else [])
        # Restore lock button icons to match lock state
        for lv in lock_vals[:NUM_SERIES]:
            is_lk = "lock" in (lv or [])
            results.append("\U0001F512\u2713" if is_lk else "\U0001F513")
        for lv in lock_vals[:NUM_SERIES]:
            is_lk = "lock" in (lv or [])
            results.append(LOCKED_ICON_STYLE if is_lk else UNLOCKED_ICON_STYLE)
        # Restore filter window values (backward-compatible: default to 1 if missing)
        filter_vals = chart_cfg.get("filter_window", [1] * NUM_SERIES)
        while len(filter_vals) < NUM_SERIES:
            filter_vals.append(1)
        for fv in filter_vals[:NUM_SERIES]:
            results.append(fv if fv else 1)
        results.append(chart_cfg.get("width", "half"))
        results.append(chart_cfg.get("height", DEFAULT_HEIGHT_PX))
        # Restore time settings (backward-compatible: sensible defaults)
        results.append(chart_cfg.get("start_time", None))
        results.append(chart_cfg.get("goto_date", ""))
        results.append(chart_cfg.get("goto_time", "00:00"))
        results.append(chart_cfg.get("win_min", 60))
        results.append(chart_cfg.get("win_hr", 0))
        results.append(chart_cfg.get("step", 15))

    return results


# ---------------------------------------------------------------------------
# Delete Setup callback — remove a saved setup from localStorage
# ---------------------------------------------------------------------------

@app.callback(
    Output("saved-setups", "data", allow_duplicate=True),
    Output("setup-status-msg", "children", allow_duplicate=True),
    Output("load-setup-dropdown", "value", allow_duplicate=True),
    Input("delete-setup-btn", "n_clicks"),
    State("load-setup-dropdown", "value"),
    State("saved-setups", "data"),
    prevent_initial_call=True,
)
def delete_setup(n_clicks, selected_name, saved):
    if not n_clicks:
        return no_update, no_update, no_update
    if not selected_name or not saved or selected_name not in saved:
        return no_update, "Select a setup to delete.", no_update

    del saved[selected_name]
    return saved, f"Deleted \"{selected_name}\".", None


# ---------------------------------------------------------------------------
# X-range tracking: store visible x-axis range when user zooms/pans
# ---------------------------------------------------------------------------

for _xi in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "x-range", "index": _xi}, "data"),
        Input({"type": "graph", "index": _xi}, "relayoutData"),
        prevent_initial_call=True,
    )
    def track_x_range(relayout_data, _cid=_xi):
        if not relayout_data:
            return no_update
        x0 = relayout_data.get("xaxis.range[0]")
        x1 = relayout_data.get("xaxis.range[1]")
        if x0 is None or x1 is None:
            return no_update
        return {"x0": str(x0), "x1": str(x1)}

    track_x_range.__name__ = f"track_x_range_{_xi}"


# ---------------------------------------------------------------------------
# Load Area button: read stored x-range and update time controls
# ---------------------------------------------------------------------------

for _li in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "start-time", "index": _li}, "data", allow_duplicate=True),
        Output({"type": "goto-date", "index": _li}, "value", allow_duplicate=True),
        Output({"type": "goto-time", "index": _li}, "value", allow_duplicate=True),
        Output({"type": "win-min", "index": _li}, "value", allow_duplicate=True),
        Output({"type": "win-hr", "index": _li}, "value", allow_duplicate=True),
        Input({"type": "load-area-btn", "index": _li}, "n_clicks"),
        State({"type": "x-range", "index": _li}, "data"),
        prevent_initial_call=True,
    )
    def load_area(n_clicks, x_range_data, _cid=_li):
        if not n_clicks or not x_range_data:
            return no_update, no_update, no_update, no_update, no_update
        x0 = x_range_data.get("x0")
        x1 = x_range_data.get("x1")
        if not x0 or not x1:
            return no_update, no_update, no_update, no_update, no_update
        try:
            t0 = pd.Timestamp(x0)
            t1 = pd.Timestamp(x1)
        except Exception:
            return no_update, no_update, no_update, no_update, no_update
        if t1 <= t0:
            return no_update, no_update, no_update, no_update, no_update
        delta = t1 - t0
        total_minutes = delta.total_seconds() / 60.0
        win_hr = int(total_minutes // 60)
        win_min = round(total_minutes - win_hr * 60)
        if win_hr == 0 and win_min == 0:
            win_min = 1
        start_iso = t0.isoformat()
        date_str = t0.strftime("%Y-%m-%d")
        time_str = t0.strftime("%H:%M")
        return start_iso, date_str, time_str, win_min, win_hr

    load_area.__name__ = f"load_area_{_li}"


# ---------------------------------------------------------------------------
# Per-series lock button toggle (click icon → flip checklist + update icon)
# ---------------------------------------------------------------------------

for _lb in range(1, MAX_CHARTS + 1):
    for _ls in range(1, NUM_SERIES + 1):
        @app.callback(
            Output({"type": "lock-scale", "chart": _lb, "series": _ls}, "value", allow_duplicate=True),
            Output({"type": "lock-scale-btn", "chart": _lb, "series": _ls}, "children", allow_duplicate=True),
            Output({"type": "lock-scale-btn", "chart": _lb, "series": _ls}, "style", allow_duplicate=True),
            Output({"type": "lock-all-state", "index": _lb}, "data", allow_duplicate=True),
            Output({"type": "lock-all-btn", "index": _lb}, "children", allow_duplicate=True),
            Output({"type": "lock-all-btn", "index": _lb}, "style", allow_duplicate=True),
            Input({"type": "lock-scale-btn", "chart": _lb, "series": _ls}, "n_clicks"),
            State({"type": "lock-scale", "chart": _lb, "series": _ls}, "value"),
            prevent_initial_call=True,
        )
        def toggle_lock_btn(n_clicks, current_val, _c=_lb, _s=_ls):
            if not n_clicks:
                return no_update, no_update, no_update, no_update, no_update, no_update
            is_locked = "lock" in (current_val or [])
            # Reset Lock All state when individual lock changes
            btn_reset_style = {**BTN_STYLE, "color": MUTED_TEXT,
                               "fontSize": "11px", "padding": "2px 10px"}
            if is_locked:
                # Unlock
                return [], "\U0001F513", UNLOCKED_ICON_STYLE, False, "\U0001F513 Lock All", btn_reset_style
            else:
                # Lock
                return ["lock"], "\U0001F512\u2713", LOCKED_ICON_STYLE, no_update, no_update, no_update

        toggle_lock_btn.__name__ = f"toggle_lock_btn_{_lb}_{_ls}"


# ---------------------------------------------------------------------------
# Lock All button: lock / unlock every series on a chart
# ---------------------------------------------------------------------------

for _la in range(1, MAX_CHARTS + 1):
    _lock_all_lock_outputs = []
    _lock_all_icon_outputs = []
    _lock_all_style_outputs = []
    for _s in range(1, NUM_SERIES + 1):
        _lock_all_lock_outputs.append(
            Output({"type": "lock-scale", "chart": _la, "series": _s}, "value", allow_duplicate=True))
        _lock_all_icon_outputs.append(
            Output({"type": "lock-scale-btn", "chart": _la, "series": _s}, "children", allow_duplicate=True))
        _lock_all_style_outputs.append(
            Output({"type": "lock-scale-btn", "chart": _la, "series": _s}, "style", allow_duplicate=True))
    @app.callback(
        Output({"type": "lock-all-state", "index": _la}, "data", allow_duplicate=True),
        Output({"type": "lock-all-btn", "index": _la}, "children", allow_duplicate=True),
        Output({"type": "lock-all-btn", "index": _la}, "style", allow_duplicate=True),
        *_lock_all_lock_outputs,
        *_lock_all_icon_outputs,
        *_lock_all_style_outputs,
        Input({"type": "lock-all-btn", "index": _la}, "n_clicks"),
        State({"type": "lock-all-state", "index": _la}, "data"),
        prevent_initial_call=True,
    )
    def toggle_lock_all(*args, _cid=_la):
        n_clicks = args[0]
        is_all_locked = args[1]
        if not n_clicks:
            return (no_update,) * (3 + NUM_SERIES * 3)
        if is_all_locked:
            # Unlock all — restore to original unlocked state
            btn_style = {**BTN_STYLE, "color": MUTED_TEXT,
                         "fontSize": "11px", "padding": "2px 10px"}
            return (
                False,
                "\U0001F513 Lock All",
                btn_style,
                *([[] for _ in range(NUM_SERIES)]),
                *(["\U0001F513" for _ in range(NUM_SERIES)]),
                *([UNLOCKED_ICON_STYLE for _ in range(NUM_SERIES)]),
            )
        else:
            # Lock all
            btn_style = {**BTN_STYLE, "color": "#3fb950",
                         "fontSize": "11px", "padding": "2px 10px"}
            return (
                True,
                "\U0001F512\u2713 Lock All",
                btn_style,
                *([["lock"] for _ in range(NUM_SERIES)]),
                *(["\U0001F512\u2713" for _ in range(NUM_SERIES)]),
                *([LOCKED_ICON_STYLE for _ in range(NUM_SERIES)]),
            )

    toggle_lock_all.__name__ = f"toggle_lock_all_{_la}"


# ---------------------------------------------------------------------------
# Autoscale X: reset X-axis to full data range, keeping Y-axes untouched
# ---------------------------------------------------------------------------

for _ax in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "start-time", "index": _ax}, "data", allow_duplicate=True),
        Output({"type": "goto-date", "index": _ax}, "value", allow_duplicate=True),
        Output({"type": "goto-time", "index": _ax}, "value", allow_duplicate=True),
        Output({"type": "win-min", "index": _ax}, "value", allow_duplicate=True),
        Output({"type": "win-hr", "index": _ax}, "value", allow_duplicate=True),
        Input({"type": "autoscale-x-btn", "index": _ax}, "n_clicks"),
        State("session-data", "data"),
        prevent_initial_call=True,
    )
    def autoscale_x(n_clicks, session_data, _cid=_ax):
        """Reset X-axis to full data range without affecting Y-axes."""
        if not n_clicks or not session_data:
            return no_update, no_update, no_update, no_update, no_update
        data_start = session_data.get("data_start")
        data_end = session_data.get("data_end")
        if not data_start or not data_end:
            return no_update, no_update, no_update, no_update, no_update
        t0 = pd.Timestamp(data_start)
        t1 = pd.Timestamp(data_end)
        delta = t1 - t0
        total_minutes = delta.total_seconds() / 60.0
        win_hr = int(total_minutes // 60)
        win_min = round(total_minutes - win_hr * 60)
        if win_hr == 0 and win_min == 0:
            win_min = 1
        return (
            t0.isoformat(),
            t0.strftime("%Y-%m-%d"),
            t0.strftime("%H:%M"),
            win_min,
            win_hr,
        )

    autoscale_x.__name__ = f"autoscale_x_{_ax}"


# ---------------------------------------------------------------------------
# Copy CSV: generate CSV text for visible data on button click (Issue #10)
# ---------------------------------------------------------------------------

for _csv in range(1, MAX_CHARTS + 1):
    _csv_series_states = [
        State({"type": "series-dd", "chart": _csv, "series": s}, "value")
        for s in range(1, NUM_SERIES + 1)
    ]

    @app.callback(
        Output({"type": "csv-data", "index": _csv}, "data"),
        Output({"type": "copy-csv-btn", "index": _csv}, "children"),
        Input({"type": "copy-csv-btn", "index": _csv}, "n_clicks"),
        State({"type": "start-time", "index": _csv}, "data"),
        State({"type": "win-min", "index": _csv}, "value"),
        State({"type": "win-hr", "index": _csv}, "value"),
        State("session-data", "data"),
        State("tag-nicknames", "data"),
        *_csv_series_states,
        prevent_initial_call=True,
    )
    def build_csv(n_clicks, start_time_iso, win_min, win_hr,
                  session_data, nn_data, *series_vals, _cid=_csv):
        if not n_clicks or not session_data:
            return no_update, no_update
        df = pd.read_json(StringIO(session_data["df_json"]), orient="split")
        if "Time" in df.columns:
            df["Time"] = pd.to_datetime(df["Time"])
        tag_map = session_data.get("tag_map", {})
        data_start = pd.Timestamp(session_data["data_start"])

        start = pd.Timestamp(start_time_iso) if start_time_iso else data_start
        w_min = (win_min or 0) + (win_hr or 0) * 60
        if w_min <= 0:
            w_min = 60
        end = start + timedelta(minutes=w_min)
        mask = (df["Time"] >= start) & (df["Time"] <= end)
        df_slice = df.loc[mask]

        # Collect active tags in order
        active_tags = [t for t in series_vals if t and t in df_slice.columns]
        if not active_tags:
            return "", "\u2398 Copy CSV"

        nn = nn_data or {}
        # Build header: Time, then "TagCode - Name [Unit]" for each tag
        headers = ["Time"]
        for tc in active_tags:
            info = tag_map.get(tc, {})
            tag_nn = nn.get(tc, {})
            name = tag_nn.get("nickname") or info.get("name", tc)
            unit = tag_nn.get("unit") or info.get("units", "")
            unit_str = f" [{unit}]" if unit else ""
            headers.append(f"{tc} - {name}{unit_str}")

        lines = [",".join(headers)]
        for _, row in df_slice.iterrows():
            vals = [row["Time"].strftime("%Y-%m-%d %H:%M:%S")]
            for tc in active_tags:
                v = row.get(tc)
                vals.append("" if pd.isna(v) else str(v))
            lines.append(",".join(vals))

        return "\n".join(lines), "\u2713 Copied!"

    build_csv.__name__ = f"build_csv_{_csv}"


# Clientside callback: copy CSV to clipboard when csv-data store updates
for _cc in range(1, MAX_CHARTS + 1):
    app.clientside_callback(
        """
        function(csv_data) {
            if (csv_data) {
                navigator.clipboard.writeText(csv_data).catch(function(){});
            }
            return "";
        }
        """,
        Output({"type": "csv-clipboard-dummy", "index": _cc}, "children"),
        Input({"type": "csv-data", "index": _cc}, "data"),
        prevent_initial_call=True,
    )


# ---------------------------------------------------------------------------
# Cursor readout: click to place cursor, Clear button to dismiss (Issue #9)
# ---------------------------------------------------------------------------

for _cur in range(1, MAX_CHARTS + 1):
    @app.callback(
        Output({"type": "cursor-ts", "index": _cur}, "data", allow_duplicate=True),
        Input({"type": "graph", "index": _cur}, "clickData"),
        Input({"type": "cursor-clear-btn", "index": _cur}, "n_clicks"),
        State({"type": "cursor-ts", "index": _cur}, "data"),
        prevent_initial_call=True,
    )
    def handle_cursor_click(click_data, clear_clicks, current_cursor, _cid=_cur):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        triggered = ctx.triggered[0]["prop_id"]
        if "cursor-clear-btn" in triggered:
            return None
        if click_data and "points" in click_data and click_data["points"]:
            x_val = click_data["points"][0].get("x")
            if x_val is not None:
                try:
                    return pd.Timestamp(x_val).isoformat()
                except Exception:
                    pass
        return no_update

    handle_cursor_click.__name__ = f"handle_cursor_click_{_cur}"


# ---------------------------------------------------------------------------
# Cursor readout: populate values at cursor timestamp (Issue #9)
# ---------------------------------------------------------------------------

for _ro in range(1, MAX_CHARTS + 1):
    _ro_series_states = [
        State({"type": "series-dd", "chart": _ro, "series": s}, "value")
        for s in range(1, NUM_SERIES + 1)
    ]

    @app.callback(
        Output({"type": "cursor-readout", "index": _ro}, "style"),
        Output({"type": "cursor-readout-text", "index": _ro}, "children"),
        Input({"type": "cursor-ts", "index": _ro}, "data"),
        State("session-data", "data"),
        State("tag-nicknames", "data"),
        *_ro_series_states,
        prevent_initial_call=True,
    )
    def update_cursor_readout(cursor_ts, session_data, nn_data, *series_vals,
                              _cid=_ro):
        if cursor_ts is None or not session_data:
            return {"display": "none"}, ""
        try:
            cursor_t = pd.Timestamp(cursor_ts)
        except Exception:
            return {"display": "none"}, ""

        df = pd.read_json(StringIO(session_data["df_json"]), orient="split")
        if "Time" in df.columns:
            df["Time"] = pd.to_datetime(df["Time"])
        tag_map = session_data.get("tag_map", {})
        nn = nn_data or {}

        parts = [html.Span(
            f"Cursor: {cursor_t.strftime('%Y-%m-%d %H:%M:%S')}  ",
            style={"color": "#d2a8ff", "fontWeight": "bold"},
        )]
        for idx, tag_code in enumerate(series_vals):
            if not tag_code or tag_code not in df.columns:
                continue
            color = TRACE_COLORS[idx % len(TRACE_COLORS)]
            info = tag_map.get(tag_code, {})
            tag_nn = nn.get(tag_code, {})
            name = tag_nn.get("nickname") or info.get("name", tag_code)
            units = tag_nn.get("unit") or info.get("units", "")
            decimals = info.get("decimals", 2)
            value = _interpolate_at(df, tag_code, cursor_t)
            if value is not None:
                try:
                    val_str = f"{value:.{int(decimals)}f}"
                except (ValueError, TypeError):
                    val_str = f"{value:.2f}"
            else:
                val_str = "N/A"
            unit_str = f" {units}" if units else ""
            parts.append(html.Span(
                f"  S{idx+1} {name}: {val_str}{unit_str}",
                style={"color": color, "fontSize": "11px"},
            ))

        return {"display": "block"}, parts

    update_cursor_readout.__name__ = f"update_cursor_readout_{_ro}"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting WtE Trend Viewer...")
    print("Open http://localhost:8050 and load an Excel file to begin.")
    app.run(debug=False, port=8050)
