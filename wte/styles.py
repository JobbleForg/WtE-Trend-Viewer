"""
Colors, style dicts, trace colors, and reusable component styles.
"""

BG_COLOR = "#0d1117"
PANEL_BG = "#161b22"
CHART_BG = "#0d1117"
GRID_COLOR = "#30363d"
TEXT_COLOR = "#c9d1d9"
ACCENT = "#58a6ff"
BORDER_COLOR = "#30363d"
MUTED_TEXT = "#8b949e"

TRACE_COLORS = [
    "#58a6ff", "#3fb950", "#f0883e", "#bc8cff", "#f778ba",
    "#79c0ff", "#ffa657", "#7ee787", "#ff7b72", "#d2a8ff",
]

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
