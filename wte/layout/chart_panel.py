"""
make_chart_panel() - builds a single chart panel with all controls.
"""

from dash import dcc, html

from wte.config import (
    NUM_SERIES, INITIAL_VISIBLE, DEFAULT_HEIGHT_PX, WIDTH_OPTIONS,
)
from wte.styles import (
    PANEL_BG, TEXT_COLOR, BORDER_COLOR, MUTED_TEXT, ACCENT,
    TRACE_COLORS, LABEL_STYLE, INPUT_STYLE, DROPDOWN_STYLE,
    BTN_STYLE, UNLOCKED_ICON_STYLE,
)


def make_chart_panel(chart_id):
    """Build a chart panel.  All MAX_CHARTS panels are pre-created in the DOM."""
    cid = str(chart_id)
    hidden = chart_id > INITIAL_VISIBLE

    dropdown_rows = []
    for row_start in (1, 6):
        row_children = []
        for s in range(row_start, min(row_start + 5, NUM_SERIES + 1)):
            color_dot = TRACE_COLORS[s - 1]
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
                dcc.Checklist(
                    id={"type": "hide-limit", "chart": chart_id, "series": s},
                    options=[{"label": "\u26A0", "value": "hide"}],
                    value=[],
                    style={"fontSize": "10px", "color": MUTED_TEXT,
                           "display": "inline-flex", "alignItems": "center",
                           "marginRight": "2px"},
                    className="hide-limit-check",
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
                html.Button("Hide All Limits", id={"type": "hide-all-limits-btn", "index": chart_id},
                            style={**BTN_STYLE, "fontSize": "10px", "padding": "2px 8px",
                                   "color": "#f0883e"},
                            title="Hide limit lines for all series on this chart"),
                html.Span("Ruler:", style={**LABEL_STYLE, "fontSize": "11px"}),
                dcc.Input(
                    id={"type": "ruler-y", "index": chart_id},
                    type="number",
                    placeholder="Y value",
                    style={**INPUT_STYLE, "width": "70px", "fontSize": "11px"},
                    debounce=True,
                ),
                html.Span("V.Ruler:", style={**LABEL_STYLE, "fontSize": "11px"}),
                dcc.Input(
                    id={"type": "ruler-time", "index": chart_id},
                    type="text",
                    placeholder="HH:MM:SS",
                    style={**INPUT_STYLE, "width": "80px", "fontSize": "11px"},
                    debounce=True,
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
            # Collapsible setup area
            html.Div(
                id={"type": "setup-area", "index": chart_id},
                style={"display": "block"},
                children=[
                    *dropdown_rows,
                    # Filter row for rolling mean
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
