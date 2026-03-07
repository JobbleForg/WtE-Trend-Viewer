"""
Add/close chart, panel style, graph height, setup area toggle.
"""

import json

from dash import ALL, Input, Output, State, callback_context, no_update

from wte.config import MAX_CHARTS, DEFAULT_HEIGHT_PX
from wte.styles import PANEL_BG, BORDER_COLOR


def register(app):
    # --- Add chart / close chart -> update visibility ---
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

        new_sync = no_update
        if new_visible is not no_update and sync_state and sync_state.get("active"):
            if sync_state.get("master") not in new_visible:
                new_sync = {"active": False, "master": None}

        return new_visible, new_sync

    # --- Panel style & graph height per chart ---
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

        update_panel_style.__name__ = f"update_panel_style_{_i}"

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

        update_graph_height.__name__ = f"update_graph_height_{_i}"

    # --- Toggle setup area ---
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
            label = "Setup \u25bc" if is_hidden else "Setup \u25b2"
            return new_style, label

        toggle_setup_area.__name__ = f"toggle_setup_area_{_st}"
