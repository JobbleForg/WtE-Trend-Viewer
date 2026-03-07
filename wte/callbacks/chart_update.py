"""
Per-chart update callback loop (series selection, time controls, scroll -> figure rebuild).
"""

from datetime import timedelta

import pandas as pd
from dash import Input, Output, State, callback_context, no_update

from wte.config import MAX_CHARTS, NUM_SERIES
from wte.data.session import get_metadata, query_time_slice
from wte.callbacks.figure import build_figure


def register(app):
    for _ci in range(1, MAX_CHARTS + 1):
        _series_inputs = [
            Input({"type": "series-dd", "chart": _ci, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]
        _own_scale_inputs = [
            Input({"type": "own-scale", "chart": _ci, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]
        _lock_scale_inputs = [
            Input({"type": "lock-scale", "chart": _ci, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]
        _filter_inputs = [
            Input({"type": "filter-window", "chart": _ci, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]
        _hide_limit_inputs = [
            Input({"type": "hide-limit", "chart": _ci, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]

        @app.callback(
            Output({"type": "graph", "index": _ci}, "figure"),
            Output({"type": "start-time", "index": _ci}, "data", allow_duplicate=True),
            Output({"type": "goto-date", "index": _ci}, "value", allow_duplicate=True),
            Output({"type": "goto-time", "index": _ci}, "value", allow_duplicate=True),
            *_series_inputs,
            *_own_scale_inputs,
            *_lock_scale_inputs,
            *_filter_inputs,
            *_hide_limit_inputs,
            Input({"type": "goto-date", "index": _ci}, "value"),
            Input({"type": "goto-time", "index": _ci}, "value"),
            Input({"type": "win-min", "index": _ci}, "value"),
            Input({"type": "win-hr", "index": _ci}, "value"),
            Input({"type": "step", "index": _ci}, "value"),
            Input({"type": "scroll-left", "index": _ci}, "n_clicks"),
            Input({"type": "scroll-right", "index": _ci}, "n_clicks"),
            Input("tag-nicknames", "data"),
            Input({"type": "show-limits", "index": _ci}, "value"),
            Input({"type": "cursor-ts", "index": _ci}, "data"),
            Input({"type": "ruler-y", "index": _ci}, "value"),
            Input({"type": "ruler-time", "index": _ci}, "value"),
            State({"type": "start-time", "index": _ci}, "data"),
            State("session-id", "data"),
            prevent_initial_call=True,
        )
        def update_chart(*args, _cid=_ci):
            tags = list(args[:NUM_SERIES])
            own_checklists = list(args[NUM_SERIES:NUM_SERIES * 2])
            own_flags = [("own" in (v or [])) for v in own_checklists]
            lock_checklists = list(args[NUM_SERIES * 2:NUM_SERIES * 3])
            lock_flags = [("lock" in (v or [])) for v in lock_checklists]
            filter_windows = list(args[NUM_SERIES * 3:NUM_SERIES * 4])
            hide_limit_checklists = list(args[NUM_SERIES * 4:NUM_SERIES * 5])
            hide_limit_flags = [("hide" in (v or [])) for v in hide_limit_checklists]
            rest = args[NUM_SERIES * 5:]
            (goto_date, goto_time, win_min, win_hr, step, n_left, n_right,
             nn_data, show_limits_val, cursor_ts_val, ruler_y_val,
             ruler_time_str, start_time_iso, session_id) = rest
            show_limits = "limits" in (show_limits_val or [])

            if not session_id:
                return build_figure(None, [], {}), no_update, no_update, no_update
            meta = get_metadata(session_id)
            if not meta:
                return build_figure(None, [], {}), no_update, no_update, no_update
            tag_map = meta["tag_map"]
            data_start = pd.Timestamp(meta["data_start"])
            data_end = pd.Timestamp(meta["data_end"])

            if data_start is None:
                return build_figure(None, [], {}), no_update, no_update, no_update

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

            active_cols = [t for t in tags if t]
            df_slice = query_time_slice(session_id, start_time, end_time, active_cols)

            # Apply rolling mean filter per series
            for idx, tag_code in enumerate(tags):
                if not tag_code or tag_code not in df_slice.columns:
                    continue
                fw = filter_windows[idx]
                try:
                    fw = int(fw) if fw else 1
                except (ValueError, TypeError):
                    fw = 1
                if fw > 1:
                    df_slice[tag_code] = (
                        df_slice[tag_code]
                        .rolling(window=fw, min_periods=1, center=True)
                        .mean()
                    )

            # Build limit overrides from tag nicknames
            limit_overrides = {}
            for tc, nn_entry in (nn_data or {}).items():
                lo = nn_entry.get("y_low")
                hi = nn_entry.get("y_high")
                if lo is not None or hi is not None:
                    limit_overrides[tc] = {}
                    if lo is not None:
                        limit_overrides[tc]["y_low"] = lo
                    if hi is not None:
                        limit_overrides[tc]["y_high"] = hi

            # Compute full vertical ruler timestamp
            ruler_time_full = None
            if ruler_time_str:
                try:
                    date_part = start_time.strftime("%Y-%m-%d")
                    ruler_time_full = f"{date_part} {ruler_time_str}"
                except Exception:
                    pass

            fig = build_figure(
                df_slice, tags, tag_map,
                x_revision=start_time.isoformat(),
                nicknames=nn_data or {},
                own_scale_flags=own_flags,
                lock_scale_flags=lock_flags,
                hide_limit_flags=hide_limit_flags,
                show_limits=show_limits,
                cursor_ts=cursor_ts_val,
                limit_overrides=limit_overrides,
                ruler_y=ruler_y_val,
                ruler_time=ruler_time_full,
            )
            return (fig, start_time.isoformat(),
                    start_time.strftime("%Y-%m-%d"),
                    start_time.strftime("%H:%M"))

        update_chart.__name__ = f"update_chart_{_ci}"
