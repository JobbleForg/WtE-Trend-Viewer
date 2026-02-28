"""
Waste-to-Energy Plant Trend Viewer
DCS-style trend display built with Dash + Plotly.
Dynamically loads data from any Excel file and displays resizable trend charts.
Each chart supports 6 independent series, each with its own Y-axis scale.
Charts can be added, removed, and resized.
"""

import os
import base64
import json
import tempfile
import pandas as pd
from datetime import timedelta
from dash import Dash, dcc, html, Input, Output, State, callback_context, no_update, ALL, MATCH
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Global mutable state
# ---------------------------------------------------------------------------

NUM_SERIES = 6
MAX_CHARTS = 8
INITIAL_VISIBLE = 4

APP_STATE = {
    "df": pd.DataFrame(),
    "tag_map": {},
    "chart_packages": [],
    "all_tags": [],
    "name_to_code": {},
    "data_start": None,
    "data_end": None,
}


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
TRACE_COLORS = ["#58a6ff", "#3fb950", "#f0883e", "#bc8cff", "#f778ba", "#79c0ff"]
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
HEIGHT_OPTIONS = [
    {"label": "Small",  "value": "200"},
    {"label": "Medium", "value": "300"},
    {"label": "Large",  "value": "450"},
    {"label": "XL",     "value": "600"},
]

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
    for row_start in (1, 4):
        row_children = []
        for s in range(row_start, row_start + 3):
            color_dot = TRACE_COLORS[s - 1]
            row_children.extend([
                html.Span(f"S{s}", style={
                    **LABEL_STYLE,
                    "color": color_dot, "fontWeight": "bold",
                    "marginLeft": "8px" if s != row_start else "0",
                }),
                dcc.Dropdown(
                    id={"type": "series-dd", "chart": chart_id, "series": s},
                    options=[], value=None,
                    placeholder=f"Series {s}", clearable=True,
                    style=DROPDOWN_STYLE, className="dark-dropdown",
                ),
            ])
        dropdown_rows.append(html.Div(style={
            "display": "flex", "alignItems": "center", "gap": "6px",
            "marginTop": "4px",
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
                dcc.Dropdown(
                    id={"type": "height-select", "index": chart_id},
                    options=HEIGHT_OPTIONS, value="300", clearable=False,
                    style={**DROPDOWN_STYLE, "width": "90px", "fontSize": "11px"},
                    className="dark-dropdown",
                ),
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
                style={"height": "300px"},
            ),
            *dropdown_rows,
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
            ]),
            dcc.Store(id={"type": "start-time", "index": chart_id}, data=None),
        ],
    )


# --- App layout ---

app.layout = html.Div(style={
    "backgroundColor": BG_COLOR, "minHeight": "100vh", "padding": "12px",
    "fontFamily": "'Segoe UI', Consolas, monospace",
}, children=[
    dcc.Store(id="temp-file-path", data=None),
    dcc.Store(id="visible-charts", data=list(range(1, INITIAL_VISIBLE + 1))),
    dcc.Store(id="saved-setups", storage_type="local", data={}),
    dcc.Store(id="sync-state", data={"active": False, "master": None}),
    dcc.Store(id="tag-nicknames", storage_type="session", data={}),

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
                    "marginBottom": "8px",
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
    Output("visible-charts", "data"),
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
        Output({"type": "chart-wrapper", "index": _i}, "style"),
        Input("visible-charts", "data"),
        Input({"type": "width-select", "index": _i}, "value"),
        Input({"type": "height-select", "index": _i}, "value"),
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
        h = int(height_val) if height_val else 300
        return {"height": f"{h}px"}


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
    prevent_initial_call=True,
)
def on_file_upload(contents, filename):
    if contents is None:
        return no_update, no_update, no_update, no_update
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    temp_path = os.path.join(tempfile.gettempdir(), f"wte_upload_{filename}")
    with open(temp_path, "wb") as f:
        f.write(decoded)
    try:
        xl = pd.ExcelFile(temp_path, engine="openpyxl")
        sheets = xl.sheet_names
        xl.close()
    except Exception as e:
        return [], None, None, f"Error: {e}"
    options = [{"label": s, "value": s} for s in sheets]
    return options, None, temp_path, filename


# ---------------------------------------------------------------------------
# Callback: Sheet selected → load data
# ---------------------------------------------------------------------------

_load_outputs = [
    Output("data-stats", "children"),
    Output("pkg-select", "options"),
]
for _c in range(1, MAX_CHARTS + 1):
    for _s in range(1, NUM_SERIES + 1):
        _load_outputs.append(Output({"type": "series-dd", "chart": _c, "series": _s}, "options"))
        _load_outputs.append(Output({"type": "series-dd", "chart": _c, "series": _s}, "value"))
    _load_outputs.append(Output({"type": "start-time", "index": _c}, "data"))
    _load_outputs.append(Output({"type": "goto-date", "index": _c}, "value"))


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
    except Exception as e:
        results = [f"Error loading sheet: {e}"]
        results.extend([no_update] * (len(_load_outputs) - 1))
        return results

    if len(df) == 0 or "Time" not in df.columns:
        results = ["No timestamp data found in this sheet."]
        results.extend([no_update] * (len(_load_outputs) - 1))
        return results

    tag_map, chart_packages = try_load_tag_refs(temp_path)
    all_tags = [c for c in df.columns if c != "Time"]
    data_start = df["Time"].iloc[0]
    data_end = df["Time"].iloc[-1]

    name_to_code = {}
    for code, info in tag_map.items():
        name_to_code[info["name"]] = code

    APP_STATE.update({
        "df": df, "tag_map": tag_map, "chart_packages": chart_packages,
        "all_tags": all_tags, "name_to_code": name_to_code,
        "data_start": data_start, "data_end": data_end,
    })

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

    results = [stats, pkg_options]
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

def _build_figure(df_slice, selected_tags, tag_map, x_revision=None, nicknames=None):
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

    # Wider offsets so axes don't overlap (3 left, 3 right max)
    axis_configs = [
        {"side": "left",  "offset": 0.0},
        {"side": "right", "offset": 0.0},
        {"side": "left",  "offset": 0.05},
        {"side": "right", "offset": 0.05},
        {"side": "left",  "offset": 0.10},
        {"side": "right", "offset": 0.10},
    ]
    active_axes = []
    for idx, tag_code in enumerate(selected_tags):
        if not tag_code or tag_code not in df_slice.columns:
            continue
        info = tag_map.get(tag_code, {})
        name = info.get("name", tag_code)
        units = info.get("units", "")

        # Apply nickname/unit overrides from Tag Manager
        tag_nn = nicknames.get(tag_code, {})
        nickname = tag_nn.get("nickname", "")
        unit_override = tag_nn.get("unit", "")
        display_name = nickname if nickname else name
        display_unit = unit_override if unit_override else units
        label = f"{display_name} [{display_unit}]" if display_unit else display_name
        color = TRACE_COLORS[idx % len(TRACE_COLORS)]
        axis_num = idx + 1
        yaxis_key = "y" if axis_num == 1 else f"y{axis_num}"
        fig.add_trace(go.Scattergl(
            x=df_slice["Time"], y=df_slice[tag_code],
            name=label, yaxis=yaxis_key,
            line=dict(color=color, width=1.5), mode="lines",
        ))
        y_range = None
        y_hi, y_lo = info.get("y_high"), info.get("y_low")
        if y_hi is not None and y_lo is not None:
            y_range = [y_lo, y_hi]
        cfg = axis_configs[idx]
        active_axes.append({
            "num": axis_num, "side": cfg["side"], "offset": cfg["offset"],
            "color": color, "range": y_range, "label": label,
            "tag_code": tag_code,
        })

    max_left = max((a["offset"] for a in active_axes if a["side"] == "left"), default=0)
    max_right = max((a["offset"] for a in active_axes if a["side"] == "right"), default=0)
    x_domain = [max_left, 1.0 - max_right]

    yaxis_layouts = {}
    for ax in active_axes:
        key = "yaxis" if ax["num"] == 1 else f"yaxis{ax['num']}"
        # Left axes stack outward (lower position = further left)
        # Right axes stack outward (higher position = further right)
        if ax["side"] == "left":
            position = max_left - ax["offset"]
        else:
            position = (1.0 - max_right) + ax["offset"]
        layout = dict(
            title=dict(text=ax["label"], font=dict(color=ax["color"], size=10)),
            tickfont=dict(color=ax["color"], size=9),
            gridcolor=GRID_COLOR if ax["num"] == 1 else "rgba(0,0,0,0)",
            showgrid=(ax["num"] == 1), zeroline=False, side=ax["side"],
            # Preserve user zoom per axis; resets only when the tag changes
            uirevision=ax["tag_code"],
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

    @app.callback(
        Output({"type": "graph", "index": _ci}, "figure"),
        Output({"type": "start-time", "index": _ci}, "data", allow_duplicate=True),
        Output({"type": "goto-date", "index": _ci}, "value", allow_duplicate=True),
        Output({"type": "goto-time", "index": _ci}, "value", allow_duplicate=True),
        *_series_inputs,
        Input({"type": "goto-date", "index": _ci}, "value"),
        Input({"type": "goto-time", "index": _ci}, "value"),
        Input({"type": "win-min", "index": _ci}, "value"),
        Input({"type": "win-hr", "index": _ci}, "value"),
        Input({"type": "step", "index": _ci}, "value"),
        Input({"type": "scroll-left", "index": _ci}, "n_clicks"),
        Input({"type": "scroll-right", "index": _ci}, "n_clicks"),
        Input("tag-nicknames", "data"),
        State({"type": "start-time", "index": _ci}, "data"),
        prevent_initial_call=True,
    )
    def update_chart(*args, _cid=_ci):
        tags = list(args[:NUM_SERIES])
        goto_date, goto_time, win_min, win_hr, step, n_left, n_right, nn_data, start_time_iso = args[NUM_SERIES:]

        df = APP_STATE["df"]
        tag_map = APP_STATE["tag_map"]
        data_start = APP_STATE["data_start"]
        data_end = APP_STATE["data_end"]

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
        df_slice = df.loc[mask]

        fig = _build_figure(df_slice, tags, tag_map,
                            x_revision=start_time.isoformat(),
                            nicknames=nn_data or {})
        return fig, start_time.isoformat(), start_time.strftime("%Y-%m-%d"), start_time.strftime("%H:%M")

    update_chart.__name__ = f"update_chart_{_ci}"


# ---------------------------------------------------------------------------
# Sync callbacks
# ---------------------------------------------------------------------------

# --- Toggle sync state when any sync button is clicked ---
@app.callback(
    Output("sync-state", "data"),
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
        is_locked = (sync_state and sync_state.get("active")
                     and sync_state.get("master") != _cid)
        if is_master:
            border = "2px solid #00e5ff"
        elif is_locked:
            border = f"1px solid {BORDER_COLOR}"
        else:
            border = f"1px solid {BORDER_COLOR}"
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
        Input("sync-state", "data"),
        prevent_initial_call=True,
    )
    def toggle_controls(sync_state, _cid=_di):
        if sync_state and sync_state.get("active"):
            if sync_state.get("master") == _cid:
                # Master: controls remain enabled
                return False, False, False, False, False, False, False
            else:
                # Locked: disable all time controls
                return True, True, True, True, True, True, True
        # Not synced: all enabled
        return False, False, False, False, False, False, False

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
# Tag Manager: populate tag rows when data is loaded
# ---------------------------------------------------------------------------

UNIT_OPTIONS = [
    {"label": u, "value": u}
    for u in ["", "m\u00b3/hr", "%", "t/hr", "mbar", "\u00b0C", "MW", "bar", "kg/s", "RPM", "mm", "l/hr"]
]


@app.callback(
    Output("tag-rows-container", "children"),
    Input("data-stats", "children"),
    State("tag-nicknames", "data"),
)
def populate_tag_rows(stats_text, saved_nicknames):
    """Rebuild the tag table rows whenever new data is loaded."""
    tag_map = APP_STATE.get("tag_map", {})
    all_tags = APP_STATE.get("all_tags", [])
    if not all_tags:
        return html.Span("No tags loaded.", style={"color": MUTED_TEXT, "fontSize": "12px"})

    if saved_nicknames is None:
        saved_nicknames = {}

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
                options=UNIT_OPTIONS,
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
    """Persist nickname and unit edits into the session store."""
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

    return current_data


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
    prevent_initial_call=True,
)
def load_chart_package(pkg_num):
    if not pkg_num:
        return [no_update] * NUM_SERIES
    name_to_code = APP_STATE["name_to_code"]
    all_tags = APP_STATE["all_tags"]
    for pkg in APP_STATE["chart_packages"]:
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
    _save_states.append(State({"type": "width-select", "index": _c}, "value"))
    _save_states.append(State({"type": "height-select", "index": _c}, "value"))


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
    *_save_states,
    prevent_initial_call=True,
)
def save_setup(n_clicks, setup_name, saved, visible, file_name, sheet_name, *chart_args):
    if not n_clicks:
        return no_update, no_update, no_update
    if not setup_name or not setup_name.strip():
        return no_update, "Enter a name first.", no_update

    setup_name = setup_name.strip()
    if saved is None:
        saved = {}

    # Parse chart_args: for each chart, NUM_SERIES dropdown values + width + height
    per_chart = NUM_SERIES + 2  # 6 series + width + height
    charts_config = {}
    for c in range(MAX_CHARTS):
        offset = c * per_chart
        series_vals = list(chart_args[offset:offset + NUM_SERIES])
        width_val = chart_args[offset + NUM_SERIES]
        height_val = chart_args[offset + NUM_SERIES + 1]
        charts_config[str(c + 1)] = {
            "series": series_vals,
            "width": width_val,
            "height": height_val,
        }

    saved[setup_name] = {
        "visible": visible,
        "charts": charts_config,
        "file_name": file_name,
        "sheet_name": sheet_name,
    }
    return saved, f"Saved \"{setup_name}\".", ""


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
]
for _c in range(1, MAX_CHARTS + 1):
    for _s in range(1, NUM_SERIES + 1):
        _load_setup_outputs.append(
            Output({"type": "series-dd", "chart": _c, "series": _s}, "value", allow_duplicate=True)
        )
    _load_setup_outputs.append(
        Output({"type": "width-select", "index": _c}, "value", allow_duplicate=True)
    )
    _load_setup_outputs.append(
        Output({"type": "height-select", "index": _c}, "value", allow_duplicate=True)
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

    results = [visible, f"Loaded \"{selected_name}\"."]

    for c in range(1, MAX_CHARTS + 1):
        chart_cfg = charts.get(str(c), {})
        series_vals = chart_cfg.get("series", [None] * NUM_SERIES)
        # Pad to NUM_SERIES if needed
        while len(series_vals) < NUM_SERIES:
            series_vals.append(None)
        for s_val in series_vals[:NUM_SERIES]:
            results.append(s_val)
        results.append(chart_cfg.get("width", "half"))
        results.append(chart_cfg.get("height", "300"))

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
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting WtE Trend Viewer...")
    print("Open http://localhost:8050 and load an Excel file to begin.")
    app.run(debug=False, port=8050)
