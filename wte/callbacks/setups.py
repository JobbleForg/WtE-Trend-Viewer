"""
Save/load/delete chart setups via browser localStorage.
"""

from datetime import datetime

from dash import Input, Output, State, no_update

from wte.config import MAX_CHARTS, NUM_SERIES, INITIAL_VISIBLE, DEFAULT_HEIGHT_PX
from wte.styles import LOCKED_ICON_STYLE, UNLOCKED_ICON_STYLE


def register(app):
    # --- Gather all State inputs for save ---
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
        for _s in range(1, NUM_SERIES + 1):
            _save_states.append(State({"type": "hide-limit", "chart": _c, "series": _s}, "value"))
        _save_states.append(State({"type": "width-select", "index": _c}, "value"))
        _save_states.append(State({"type": "height-select", "index": _c}, "value"))
        _save_states.append(State({"type": "start-time", "index": _c}, "data"))
        _save_states.append(State({"type": "goto-date", "index": _c}, "value"))
        _save_states.append(State({"type": "goto-time", "index": _c}, "value"))
        _save_states.append(State({"type": "win-min", "index": _c}, "value"))
        _save_states.append(State({"type": "win-hr", "index": _c}, "value"))
        _save_states.append(State({"type": "step", "index": _c}, "value"))

    # --- Save Setup ---
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
    def save_setup(n_clicks, setup_name, saved, visible, file_name, sheet_name,
                   sync_state, *chart_args):
        if not n_clicks:
            return no_update, no_update, no_update
        if not setup_name or not setup_name.strip():
            return no_update, "Enter a name first.", no_update

        setup_name = setup_name.strip()
        if saved is None:
            saved = {}

        per_chart = NUM_SERIES * 5 + 8
        charts_config = {}
        for c in range(MAX_CHARTS):
            offset = c * per_chart
            series_vals = list(chart_args[offset:offset + NUM_SERIES])
            own_vals = list(chart_args[offset + NUM_SERIES:offset + NUM_SERIES * 2])
            lock_vals = list(chart_args[offset + NUM_SERIES * 2:offset + NUM_SERIES * 3])
            filter_vals = list(chart_args[offset + NUM_SERIES * 3:offset + NUM_SERIES * 4])
            hide_limit_vals = list(chart_args[offset + NUM_SERIES * 4:offset + NUM_SERIES * 5])
            width_val = chart_args[offset + NUM_SERIES * 5]
            height_val = chart_args[offset + NUM_SERIES * 5 + 1]
            start_time_val = chart_args[offset + NUM_SERIES * 5 + 2]
            goto_date_val = chart_args[offset + NUM_SERIES * 5 + 3]
            goto_time_val = chart_args[offset + NUM_SERIES * 5 + 4]
            win_min_val = chart_args[offset + NUM_SERIES * 5 + 5]
            win_hr_val = chart_args[offset + NUM_SERIES * 5 + 6]
            step_val = chart_args[offset + NUM_SERIES * 5 + 7]
            charts_config[str(c + 1)] = {
                "series": series_vals,
                "own_scale": own_vals,
                "lock_scale": lock_vals,
                "filter_window": filter_vals,
                "hide_limit": hide_limit_vals,
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
        return saved, f'Saved "{setup_name}" at {now}.', ""

    # --- Update load-setup dropdown ---
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

    # --- Load Setup ---
    _load_setup_outputs = [
        Output("visible-charts", "data", allow_duplicate=True),
        Output("setup-status-msg", "children", allow_duplicate=True),
        Output("sync-state", "data", allow_duplicate=True),
    ]
    for _c in range(1, MAX_CHARTS + 1):
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "series-dd", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "own-scale", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "lock-scale", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "lock-scale-btn", "chart": _c, "series": _s}, "children", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "lock-scale-btn", "chart": _c, "series": _s}, "style", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "filter-window", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _load_setup_outputs.append(
                Output({"type": "hide-limit", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "width-select", "index": _c}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "height-select", "index": _c}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "start-time", "index": _c}, "data", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "goto-date", "index": _c}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "goto-time", "index": _c}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "win-min", "index": _c}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "win-hr", "index": _c}, "value", allow_duplicate=True))
        _load_setup_outputs.append(
            Output({"type": "step", "index": _c}, "value", allow_duplicate=True))

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
        results = [visible, f'Loaded "{selected_name}".', sync_state]

        for c in range(1, MAX_CHARTS + 1):
            chart_cfg = charts.get(str(c), {})
            series_vals = chart_cfg.get("series", [None] * NUM_SERIES)
            while len(series_vals) < NUM_SERIES:
                series_vals.append(None)
            for s_val in series_vals[:NUM_SERIES]:
                results.append(s_val)
            own_vals = chart_cfg.get("own_scale", [[] for _ in range(NUM_SERIES)])
            while len(own_vals) < NUM_SERIES:
                own_vals.append([])
            for ov in own_vals[:NUM_SERIES]:
                results.append(ov if ov else [])
            lock_vals = chart_cfg.get("lock_scale", [[] for _ in range(NUM_SERIES)])
            while len(lock_vals) < NUM_SERIES:
                lock_vals.append([])
            for lv in lock_vals[:NUM_SERIES]:
                results.append(lv if lv else [])
            for lv in lock_vals[:NUM_SERIES]:
                is_lk = "lock" in (lv or [])
                results.append("\U0001f512\u2713" if is_lk else "\U0001f513")
            for lv in lock_vals[:NUM_SERIES]:
                is_lk = "lock" in (lv or [])
                results.append(LOCKED_ICON_STYLE if is_lk else UNLOCKED_ICON_STYLE)
            filter_vals = chart_cfg.get("filter_window", [1] * NUM_SERIES)
            while len(filter_vals) < NUM_SERIES:
                filter_vals.append(1)
            for fv in filter_vals[:NUM_SERIES]:
                results.append(fv if fv else 1)
            hide_limit_vals = chart_cfg.get("hide_limit", [[] for _ in range(NUM_SERIES)])
            while len(hide_limit_vals) < NUM_SERIES:
                hide_limit_vals.append([])
            for hlv in hide_limit_vals[:NUM_SERIES]:
                results.append(hlv if hlv else [])
            results.append(chart_cfg.get("width", "half"))
            results.append(chart_cfg.get("height", DEFAULT_HEIGHT_PX))
            results.append(chart_cfg.get("start_time", None))
            results.append(chart_cfg.get("goto_date", ""))
            results.append(chart_cfg.get("goto_time", "00:00"))
            results.append(chart_cfg.get("win_min", 60))
            results.append(chart_cfg.get("win_hr", 0))
            results.append(chart_cfg.get("step", 15))

        return results

    # --- Delete Setup ---
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
        return saved, f'Deleted "{selected_name}".', None

    # Export _save_states for use by session_restore
    app._wte_save_states = _save_states
