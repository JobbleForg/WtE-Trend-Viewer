"""
Root layout assembly: stores, header, chart grid, tag manager,
notes overlay, custom CSS index_string.
"""

from dash import dcc, html

from wte.config import MAX_CHARTS, INITIAL_VISIBLE
from wte.styles import (
    BG_COLOR, PANEL_BG, CHART_BG, TEXT_COLOR, ACCENT,
    BORDER_COLOR, MUTED_TEXT, BTN_STYLE,
)
from wte.data.persistence import INIT_NICKNAMES, INIT_CUSTOM_UNITS
from wte.layout.chart_panel import make_chart_panel
from wte.layout.header import build_header
from wte.layout.tag_manager import build_tag_manager_panel


def _build_notes_overlay():
    """Return the notes overlay panel (Issue #12)."""
    return html.Div(
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
    )


def build_layout():
    """Return the complete app layout."""
    return html.Div(style={
        "backgroundColor": BG_COLOR, "minHeight": "100vh", "padding": "12px",
        "fontFamily": "'Segoe UI', Consolas, monospace",
    }, children=[
        dcc.Store(id="temp-file-path", data=None),
        dcc.Store(id="session-id", storage_type="memory", data=None),
        dcc.Store(id="visible-charts", data=list(range(1, INITIAL_VISIBLE + 1))),
        dcc.Store(id="saved-setups", storage_type="local", data={}),
        dcc.Store(id="sync-state", data={"active": False, "master": None}),
        dcc.Store(id="tag-nicknames", storage_type="memory", data=INIT_NICKNAMES),
        dcc.Store(id="custom-units", storage_type="memory", data=INIT_CUSTOM_UNITS),
        dcc.Store(id="notes-text", storage_type="local", data=""),
        dcc.Store(id="autoload-config", storage_type="local", data=None),
        dcc.Interval(id="autosave-interval", interval=15_000, n_intervals=0),
        dcc.Interval(id="autoload-trigger", interval=500, max_intervals=1, n_intervals=0),

        _build_notes_overlay(),
        build_header(),

        # Data stats bar
        html.Div(id="data-stats", style={
            "padding": "4px 12px", "marginBottom": "8px",
            "color": MUTED_TEXT, "fontSize": "12px",
        }, children="Load an Excel file and select a data sheet to begin."),

        # Chart container - flexbox wrap
        html.Div(
            id="chart-container",
            style={
                "display": "flex", "flexWrap": "wrap", "gap": "10px",
            },
            children=[make_chart_panel(i) for i in range(1, MAX_CHARTS + 1)],
        ),

        build_tag_manager_panel(),
    ])


def get_index_string():
    """Return the custom HTML template with dark theme CSS."""
    return '''<!DOCTYPE html>
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
        input:disabled, button:disabled {
            opacity: 0.4 !important;
            cursor: not-allowed !important;
        }
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
