"""
Tag Manager collapsible panel layout + unit options constant.
"""

from dash import dcc, html

from wte.styles import (
    ACCENT, MUTED_TEXT, BORDER_COLOR,
    LABEL_STYLE, INPUT_STYLE, DROPDOWN_STYLE, BTN_STYLE,
)


UNIT_OPTIONS = [
    {"label": u, "value": u}
    for u in [
        "", "m\u00b3/hr", "%", "t/hr", "mbar", "\u00b0C",
        "MW", "bar", "kg/s", "RPM", "mm", "l/hr",
    ]
]

# Set of built-in unit values for duplicate checking
BUILTIN_UNITS = {opt["value"] for opt in UNIT_OPTIONS}


def build_tag_manager_panel():
    """Return the collapsible Tag Manager panel."""
    return html.Div(style={"marginTop": "12px"}, children=[
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
                "backgroundColor": "#161b22",
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
                    "gridTemplateColumns": "1fr 1.5fr 1fr 1fr 0.7fr 0.7fr",
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
                    html.Span("Limit Low", style={
                        "color": ACCENT, "fontSize": "11px",
                        "fontWeight": "bold",
                    }),
                    html.Span("Limit High", style={
                        "color": ACCENT, "fontSize": "11px",
                        "fontWeight": "bold",
                    }),
                ]),
                # Tag rows container (populated dynamically)
                html.Div(id="tag-rows-container"),
            ],
        ),
    ])
