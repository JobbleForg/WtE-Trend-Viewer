"""
Header toolbar: title, upload button, sheet/package dropdowns,
setup save/load, notes button.
"""

from dash import dcc, html

from wte.styles import (
    ACCENT, MUTED_TEXT, BORDER_COLOR,
    LABEL_STYLE, INPUT_STYLE, DROPDOWN_STYLE, BTN_STYLE,
)


def build_header():
    """Return the header toolbar Div."""
    return html.Div(style={
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
        # Save / Load Setup controls
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
    ])
