"""
Toggle sync, propagate time, sync border/button/controls, zoom sync.
"""

import json

import pandas as pd
from dash import Input, Output, State, callback_context, no_update

from wte.config import MAX_CHARTS
from wte.styles import PANEL_BG, BORDER_COLOR, MUTED_TEXT, BTN_STYLE


def register(app):
    # --- Toggle sync state ---
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
            if sync_state.get("master") == chart_id:
                return {"active": False, "master": None}
            return no_update
        else:
            return {"active": True, "master": chart_id}

    # --- Propagate master time settings ---
    for _si in range(1, MAX_CHARTS + 1):
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
            results = []
            for t in _targets:
                if t in (visible or []):
                    results.extend([start_iso, goto_date, goto_time, win_min, win_hr, step])
                else:
                    results.extend([no_update] * 6)
            return results

        propagate_sync.__name__ = f"propagate_sync_{_si}"

    # --- Sync border style ---
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

    # --- Sync button label ---
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
                    return ("\U0001f517 Unsync", {
                        **BTN_STYLE, "color": "#0d1117",
                        "backgroundColor": "#00e5ff",
                        "fontSize": "11px", "padding": "2px 10px",
                        "fontWeight": "bold",
                    })
                else:
                    return ("\U0001f512 Locked", {
                        **BTN_STYLE, "color": MUTED_TEXT,
                        "fontSize": "11px", "padding": "2px 10px",
                        "cursor": "default", "opacity": "0.6",
                    })
            return ("\U0001f517 Sync", {
                **BTN_STYLE, "color": "#58a6ff",
                "fontSize": "11px", "padding": "2px 10px",
            })

        update_sync_btn.__name__ = f"update_sync_btn_{_bi}"

    # --- Disable/enable time controls ---
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
                    return False, False, False, False, False, False, False, False
                else:
                    return True, True, True, True, True, True, True, True
            return False, False, False, False, False, False, False, False

        toggle_controls.__name__ = f"toggle_controls_{_di}"

    # --- Zoom sync ---
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

        triggered = ctx.triggered[0]["prop_id"]
        try:
            prop = json.loads(triggered.rsplit(".", 1)[0])
            triggered_chart = prop["index"]
        except Exception:
            return [no_update] * n_total

        if triggered_chart != master:
            return [no_update] * n_total

        relayout = relayout_list[master - 1]
        if not relayout:
            return [no_update] * n_total

        x0 = relayout.get("xaxis.range[0]")
        x1 = relayout.get("xaxis.range[1]")

        if x0 is None or x1 is None:
            return [no_update] * n_total

        try:
            t0 = pd.Timestamp(x0)
            t1 = pd.Timestamp(x1)
        except Exception:
            return [no_update] * n_total

        if t1 <= t0:
            return [no_update] * n_total

        delta = t1 - t0
        total_minutes = delta.total_seconds() / 60.0
        win_hr = int(total_minutes // 60)
        win_min = round(total_minutes - win_hr * 60)
        if win_hr == 0 and win_min == 0:
            win_min = 1

        start_iso = t0.isoformat()
        date_str = t0.strftime("%Y-%m-%d")
        time_str = t0.strftime("%H:%M")

        results = []
        for ci in range(1, MAX_CHARTS + 1):
            if ci in (visible or []):
                results.extend([start_iso, date_str, time_str, win_min, win_hr])
            else:
                results.extend([no_update] * 5)
        return results
