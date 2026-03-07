"""
Autoload last session on page load + periodic autosave.
"""

import os
import uuid

import pandas as pd
from dash import Input, Output, State, no_update

from wte.config import (
    MAX_CHARTS, NUM_SERIES, INITIAL_VISIBLE, DEFAULT_HEIGHT_PX,
    LAST_SESSION_DIR,
)
from wte.styles import LOCKED_ICON_STYLE, UNLOCKED_ICON_STYLE
from wte.data.loader import load_sheet_data, try_load_tag_refs, tag_label
from wte.data.session import create_session_db


def register(app):
    # --- Build autosave state list (must match setups._save_states but without hide-limit) ---
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

    # --- Autoload ---
    _autoload_outputs = [
        Output("session-id", "data", allow_duplicate=True),
        Output("data-stats", "children", allow_duplicate=True),
        Output("pkg-select", "options", allow_duplicate=True),
        Output("temp-file-path", "data", allow_duplicate=True),
        Output("file-name-display", "children", allow_duplicate=True),
        Output("sheet-select", "options", allow_duplicate=True),
        Output("sheet-select", "value", allow_duplicate=True),
        Output("visible-charts", "data", allow_duplicate=True),
        Output("sync-state", "data", allow_duplicate=True),
    ]
    for _c in range(1, MAX_CHARTS + 1):
        for _s in range(1, NUM_SERIES + 1):
            _autoload_outputs.append(
                Output({"type": "series-dd", "chart": _c, "series": _s}, "options", allow_duplicate=True))
            _autoload_outputs.append(
                Output({"type": "series-dd", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _autoload_outputs.append(
                Output({"type": "own-scale", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _autoload_outputs.append(
                Output({"type": "lock-scale", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _autoload_outputs.append(
                Output({"type": "lock-scale-btn", "chart": _c, "series": _s}, "children", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _autoload_outputs.append(
                Output({"type": "lock-scale-btn", "chart": _c, "series": _s}, "style", allow_duplicate=True))
        for _s in range(1, NUM_SERIES + 1):
            _autoload_outputs.append(
                Output({"type": "filter-window", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "width-select", "index": _c}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "height-select", "index": _c}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "start-time", "index": _c}, "data", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "goto-date", "index": _c}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "goto-time", "index": _c}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "win-min", "index": _c}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "win-hr", "index": _c}, "value", allow_duplicate=True))
        _autoload_outputs.append(Output({"type": "step", "index": _c}, "value", allow_duplicate=True))

    @app.callback(
        _autoload_outputs,
        Input("autoload-trigger", "n_intervals"),
        State("autoload-config", "data"),
        prevent_initial_call=True,
    )
    def autoload_last_session(n_intervals, config):
        no_change = [no_update] * len(_autoload_outputs)
        if not config:
            return no_change
        file_path = config.get("file_path")
        file_name = config.get("file_name")
        sheet_name = config.get("sheet_name")
        if not file_path or not os.path.isfile(file_path) or not sheet_name:
            return no_change
        try:
            df = load_sheet_data(file_path, sheet_name)
            tag_map, chart_packages = try_load_tag_refs(file_path)
        except Exception:
            return no_change
        if len(df) == 0 or "Time" not in df.columns:
            return no_change

        all_tags = [c for c in df.columns if c != "Time"]
        data_start = df["Time"].iloc[0]
        data_end = df["Time"].iloc[-1]
        name_to_code = {}
        for code, info in tag_map.items():
            name_to_code[info["name"]] = code
        session_id = str(uuid.uuid4())
        create_session_db(session_id, df, tag_map, chart_packages, all_tags,
                          name_to_code, data_start, data_end)
        stats = (
            f"Start: {data_start.strftime('%Y-%m-%d %H:%M')}  |  "
            f"End: {data_end.strftime('%Y-%m-%d %H:%M')}  |  "
            f"Data points: {len(df):,}  |  "
            f"Tags: {len(all_tags)}  |  "
            f"(Auto-loaded)"
        )
        tag_options = [{"label": tag_label(c, tag_map), "value": c} for c in all_tags]
        pkg_options = [{"label": "-- None --", "value": ""}]
        for pkg in chart_packages:
            names = [n for n in pkg["tags"] if n]
            pkg_options.append({
                "label": f"Pkg {pkg['num']}: {' / '.join(names)}",
                "value": pkg["num"],
            })
        try:
            xl = pd.ExcelFile(file_path, engine="openpyxl")
            sheet_options = [{"label": s, "value": s} for s in xl.sheet_names]
            xl.close()
        except Exception:
            sheet_options = [{"label": sheet_name, "value": sheet_name}]

        visible = config.get("visible", list(range(1, INITIAL_VISIBLE + 1)))
        charts = config.get("charts", {})
        sync_state = config.get("sync_state", {"active": False, "master": None})

        results = [
            session_id, stats, pkg_options, file_path, file_name,
            sheet_options, sheet_name, visible, sync_state,
        ]

        for c in range(1, MAX_CHARTS + 1):
            chart_cfg = charts.get(str(c), {})
            series_vals = chart_cfg.get("series", [None] * NUM_SERIES)
            while len(series_vals) < NUM_SERIES:
                series_vals.append(None)
            for s_val in series_vals[:NUM_SERIES]:
                results.append(tag_options)
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
            results.append(chart_cfg.get("width", "half"))
            results.append(chart_cfg.get("height", DEFAULT_HEIGHT_PX))
            results.append(chart_cfg.get("start_time", None))
            results.append(chart_cfg.get("goto_date", ""))
            results.append(chart_cfg.get("goto_time", "00:00"))
            results.append(chart_cfg.get("win_min", 60))
            results.append(chart_cfg.get("win_hr", 0))
            results.append(chart_cfg.get("step", 15))

        return results

    # --- Autosave ---
    @app.callback(
        Output("autoload-config", "data"),
        Input("autosave-interval", "n_intervals"),
        State("session-id", "data"),
        State("file-name-display", "children"),
        State("sheet-select", "value"),
        State("visible-charts", "data"),
        State("sync-state", "data"),
        *_save_states,
        prevent_initial_call=True,
    )
    def autosave_session(n_intervals, session_id, file_name, sheet_name,
                         visible, sync_state, *chart_args):
        if not session_id or not file_name or not sheet_name:
            return no_update

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

        persistent_path = os.path.join(LAST_SESSION_DIR, file_name) if file_name else None
        return {
            "file_name": file_name,
            "file_path": persistent_path,
            "sheet_name": sheet_name,
            "visible": visible,
            "sync_state": sync_state,
            "charts": charts_config,
        }
