"""
Load Area, Lock scale, Hide limits, Autoscale X, Copy CSV, Cursor readout,
X-range tracking.
"""

from datetime import timedelta

import pandas as pd
from dash import Input, Output, State, callback_context, html, no_update

from wte.config import MAX_CHARTS, NUM_SERIES
from wte.styles import (
    MUTED_TEXT, TEXT_COLOR, TRACE_COLORS,
    BTN_STYLE, LOCKED_ICON_STYLE, UNLOCKED_ICON_STYLE,
)
from wte.data.session import get_metadata, query_full_data
from wte.callbacks.figure import _interpolate_at


def register(app):
    # --- X-range tracking ---
    for _xi in range(1, MAX_CHARTS + 1):
        @app.callback(
            Output({"type": "x-range", "index": _xi}, "data"),
            Input({"type": "graph", "index": _xi}, "relayoutData"),
            prevent_initial_call=True,
        )
        def track_x_range(relayout_data, _cid=_xi):
            if not relayout_data:
                return no_update
            x0 = relayout_data.get("xaxis.range[0]")
            x1 = relayout_data.get("xaxis.range[1]")
            if x0 is None or x1 is None:
                return no_update
            return {"x0": str(x0), "x1": str(x1)}

        track_x_range.__name__ = f"track_x_range_{_xi}"

    # --- Load Area ---
    for _li in range(1, MAX_CHARTS + 1):
        @app.callback(
            Output({"type": "start-time", "index": _li}, "data", allow_duplicate=True),
            Output({"type": "goto-date", "index": _li}, "value", allow_duplicate=True),
            Output({"type": "goto-time", "index": _li}, "value", allow_duplicate=True),
            Output({"type": "win-min", "index": _li}, "value", allow_duplicate=True),
            Output({"type": "win-hr", "index": _li}, "value", allow_duplicate=True),
            Input({"type": "load-area-btn", "index": _li}, "n_clicks"),
            State({"type": "x-range", "index": _li}, "data"),
            prevent_initial_call=True,
        )
        def load_area(n_clicks, x_range_data, _cid=_li):
            if not n_clicks or not x_range_data:
                return no_update, no_update, no_update, no_update, no_update
            x0 = x_range_data.get("x0")
            x1 = x_range_data.get("x1")
            if not x0 or not x1:
                return no_update, no_update, no_update, no_update, no_update
            try:
                t0 = pd.Timestamp(x0)
                t1 = pd.Timestamp(x1)
            except Exception:
                return no_update, no_update, no_update, no_update, no_update
            if t1 <= t0:
                return no_update, no_update, no_update, no_update, no_update
            delta = t1 - t0
            total_minutes = delta.total_seconds() / 60.0
            win_hr = int(total_minutes // 60)
            win_min = round(total_minutes - win_hr * 60)
            if win_hr == 0 and win_min == 0:
                win_min = 1
            return (t0.isoformat(), t0.strftime("%Y-%m-%d"),
                    t0.strftime("%H:%M"), win_min, win_hr)

        load_area.__name__ = f"load_area_{_li}"

    # --- Per-series lock button toggle ---
    for _lb in range(1, MAX_CHARTS + 1):
        for _ls in range(1, NUM_SERIES + 1):
            @app.callback(
                Output({"type": "lock-scale", "chart": _lb, "series": _ls}, "value", allow_duplicate=True),
                Output({"type": "lock-scale-btn", "chart": _lb, "series": _ls}, "children", allow_duplicate=True),
                Output({"type": "lock-scale-btn", "chart": _lb, "series": _ls}, "style", allow_duplicate=True),
                Output({"type": "lock-all-state", "index": _lb}, "data", allow_duplicate=True),
                Output({"type": "lock-all-btn", "index": _lb}, "children", allow_duplicate=True),
                Output({"type": "lock-all-btn", "index": _lb}, "style", allow_duplicate=True),
                Input({"type": "lock-scale-btn", "chart": _lb, "series": _ls}, "n_clicks"),
                State({"type": "lock-scale", "chart": _lb, "series": _ls}, "value"),
                prevent_initial_call=True,
            )
            def toggle_lock_btn(n_clicks, current_val, _c=_lb, _s=_ls):
                if not n_clicks:
                    return no_update, no_update, no_update, no_update, no_update, no_update
                is_locked = "lock" in (current_val or [])
                btn_reset_style = {**BTN_STYLE, "color": MUTED_TEXT,
                                   "fontSize": "11px", "padding": "2px 10px"}
                if is_locked:
                    return [], "\U0001f513", UNLOCKED_ICON_STYLE, False, "\U0001f513 Lock All", btn_reset_style
                else:
                    return ["lock"], "\U0001f512\u2713", LOCKED_ICON_STYLE, no_update, no_update, no_update

            toggle_lock_btn.__name__ = f"toggle_lock_btn_{_lb}_{_ls}"

    # --- Lock All button ---
    for _la in range(1, MAX_CHARTS + 1):
        _lock_all_lock_outputs = []
        _lock_all_icon_outputs = []
        _lock_all_style_outputs = []
        for _s in range(1, NUM_SERIES + 1):
            _lock_all_lock_outputs.append(
                Output({"type": "lock-scale", "chart": _la, "series": _s}, "value", allow_duplicate=True))
            _lock_all_icon_outputs.append(
                Output({"type": "lock-scale-btn", "chart": _la, "series": _s}, "children", allow_duplicate=True))
            _lock_all_style_outputs.append(
                Output({"type": "lock-scale-btn", "chart": _la, "series": _s}, "style", allow_duplicate=True))

        @app.callback(
            Output({"type": "lock-all-state", "index": _la}, "data", allow_duplicate=True),
            Output({"type": "lock-all-btn", "index": _la}, "children", allow_duplicate=True),
            Output({"type": "lock-all-btn", "index": _la}, "style", allow_duplicate=True),
            *_lock_all_lock_outputs,
            *_lock_all_icon_outputs,
            *_lock_all_style_outputs,
            Input({"type": "lock-all-btn", "index": _la}, "n_clicks"),
            State({"type": "lock-all-state", "index": _la}, "data"),
            prevent_initial_call=True,
        )
        def toggle_lock_all(*args, _cid=_la):
            n_clicks = args[0]
            is_all_locked = args[1]
            if not n_clicks:
                return (no_update,) * (3 + NUM_SERIES * 3)
            if is_all_locked:
                btn_style = {**BTN_STYLE, "color": MUTED_TEXT,
                             "fontSize": "11px", "padding": "2px 10px"}
                return (
                    False,
                    "\U0001f513 Lock All",
                    btn_style,
                    *([[] for _ in range(NUM_SERIES)]),
                    *(["\U0001f513" for _ in range(NUM_SERIES)]),
                    *([UNLOCKED_ICON_STYLE for _ in range(NUM_SERIES)]),
                )
            else:
                btn_style = {**BTN_STYLE, "color": "#3fb950",
                             "fontSize": "11px", "padding": "2px 10px"}
                return (
                    True,
                    "\U0001f512\u2713 Lock All",
                    btn_style,
                    *([["lock"] for _ in range(NUM_SERIES)]),
                    *(["\U0001f512\u2713" for _ in range(NUM_SERIES)]),
                    *([LOCKED_ICON_STYLE for _ in range(NUM_SERIES)]),
                )

        toggle_lock_all.__name__ = f"toggle_lock_all_{_la}"

    # --- Hide All Limits ---
    for _hal in range(1, MAX_CHARTS + 1):
        _hide_all_outputs = [
            Output({"type": "hide-limit", "chart": _hal, "series": _s}, "value", allow_duplicate=True)
            for _s in range(1, NUM_SERIES + 1)
        ]

        @app.callback(
            *_hide_all_outputs,
            Input({"type": "hide-all-limits-btn", "index": _hal}, "n_clicks"),
            [State({"type": "hide-limit", "chart": _hal, "series": _s}, "value")
             for _s in range(1, NUM_SERIES + 1)],
            prevent_initial_call=True,
        )
        def hide_all_limits(*args, _cid=_hal):
            n_clicks = args[0]
            current_vals = args[1:]
            if not n_clicks:
                return (no_update,) * NUM_SERIES
            any_visible = any("hide" not in (v or []) for v in current_vals)
            if any_visible:
                return (["hide"],) * NUM_SERIES
            else:
                return ([],) * NUM_SERIES

        hide_all_limits.__name__ = f"hide_all_limits_{_hal}"

    # --- Autoscale X ---
    for _ax in range(1, MAX_CHARTS + 1):
        @app.callback(
            Output({"type": "start-time", "index": _ax}, "data", allow_duplicate=True),
            Output({"type": "goto-date", "index": _ax}, "value", allow_duplicate=True),
            Output({"type": "goto-time", "index": _ax}, "value", allow_duplicate=True),
            Output({"type": "win-min", "index": _ax}, "value", allow_duplicate=True),
            Output({"type": "win-hr", "index": _ax}, "value", allow_duplicate=True),
            Input({"type": "autoscale-x-btn", "index": _ax}, "n_clicks"),
            State("session-id", "data"),
            prevent_initial_call=True,
        )
        def autoscale_x(n_clicks, session_id, _cid=_ax):
            if not n_clicks or not session_id:
                return no_update, no_update, no_update, no_update, no_update
            meta = get_metadata(session_id)
            if not meta:
                return no_update, no_update, no_update, no_update, no_update
            data_start = meta.get("data_start")
            data_end = meta.get("data_end")
            if not data_start or not data_end:
                return no_update, no_update, no_update, no_update, no_update
            t0 = pd.Timestamp(data_start)
            t1 = pd.Timestamp(data_end)
            delta = t1 - t0
            total_minutes = delta.total_seconds() / 60.0
            win_hr = int(total_minutes // 60)
            win_min = round(total_minutes - win_hr * 60)
            if win_hr == 0 and win_min == 0:
                win_min = 1
            return (t0.isoformat(), t0.strftime("%Y-%m-%d"),
                    t0.strftime("%H:%M"), win_min, win_hr)

        autoscale_x.__name__ = f"autoscale_x_{_ax}"

    # --- Copy CSV ---
    for _csv in range(1, MAX_CHARTS + 1):
        _csv_series_states = [
            State({"type": "series-dd", "chart": _csv, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]

        @app.callback(
            Output({"type": "csv-data", "index": _csv}, "data"),
            Output({"type": "copy-csv-btn", "index": _csv}, "children"),
            Input({"type": "copy-csv-btn", "index": _csv}, "n_clicks"),
            State({"type": "start-time", "index": _csv}, "data"),
            State({"type": "win-min", "index": _csv}, "value"),
            State({"type": "win-hr", "index": _csv}, "value"),
            State("session-id", "data"),
            State("tag-nicknames", "data"),
            *_csv_series_states,
            prevent_initial_call=True,
        )
        def build_csv(n_clicks, start_time_iso, win_min, win_hr,
                      session_id, nn_data, *series_vals, _cid=_csv):
            from wte.data.session import query_time_slice
            if not n_clicks or not session_id:
                return no_update, no_update
            meta = get_metadata(session_id)
            if not meta:
                return no_update, no_update
            tag_map = meta.get("tag_map", {})
            data_start = pd.Timestamp(meta["data_start"])
            start = pd.Timestamp(start_time_iso) if start_time_iso else data_start
            w_min = (win_min or 0) + (win_hr or 0) * 60
            if w_min <= 0:
                w_min = 60
            end = start + timedelta(minutes=w_min)
            active_cols = [t for t in series_vals if t]
            df_slice = query_time_slice(session_id, start, end, active_cols)
            active_tags = [t for t in series_vals if t and t in df_slice.columns]
            if not active_tags:
                return "", "\u2398 Copy CSV"

            nn = nn_data or {}
            headers = ["Time"]
            for tc in active_tags:
                info = tag_map.get(tc, {})
                tag_nn = nn.get(tc, {})
                name = tag_nn.get("nickname") or info.get("name", tc)
                unit = tag_nn.get("unit") or info.get("units", "")
                unit_str = f" [{unit}]" if unit else ""
                headers.append(f"{tc} - {name}{unit_str}")

            lines = [",".join(headers)]
            for _, row in df_slice.iterrows():
                vals = [row["Time"].strftime("%Y-%m-%d %H:%M:%S")]
                for tc in active_tags:
                    v = row.get(tc)
                    vals.append("" if pd.isna(v) else str(v))
                lines.append(",".join(vals))

            return "\n".join(lines), "\u2713 Copied!"

        build_csv.__name__ = f"build_csv_{_csv}"

    # --- CSV clipboard clientside callback ---
    for _cc in range(1, MAX_CHARTS + 1):
        app.clientside_callback(
            """
            function(csv_data) {
                if (csv_data) {
                    navigator.clipboard.writeText(csv_data).catch(function(){});
                }
                return "";
            }
            """,
            Output({"type": "csv-clipboard-dummy", "index": _cc}, "children"),
            Input({"type": "csv-data", "index": _cc}, "data"),
            prevent_initial_call=True,
        )

    # --- Cursor readout: click/clear ---
    for _cur in range(1, MAX_CHARTS + 1):
        @app.callback(
            Output({"type": "cursor-ts", "index": _cur}, "data", allow_duplicate=True),
            Input({"type": "graph", "index": _cur}, "clickData"),
            Input({"type": "cursor-clear-btn", "index": _cur}, "n_clicks"),
            State({"type": "cursor-ts", "index": _cur}, "data"),
            prevent_initial_call=True,
        )
        def handle_cursor_click(click_data, clear_clicks, current_cursor, _cid=_cur):
            ctx = callback_context
            if not ctx.triggered:
                return no_update
            triggered = ctx.triggered[0]["prop_id"]
            if "cursor-clear-btn" in triggered:
                return None
            if click_data and "points" in click_data and click_data["points"]:
                x_val = click_data["points"][0].get("x")
                if x_val is not None:
                    try:
                        return pd.Timestamp(x_val).isoformat()
                    except Exception:
                        pass
            return no_update

        handle_cursor_click.__name__ = f"handle_cursor_click_{_cur}"

    # --- Cursor readout: populate values ---
    for _ro in range(1, MAX_CHARTS + 1):
        _ro_series_states = [
            State({"type": "series-dd", "chart": _ro, "series": s}, "value")
            for s in range(1, NUM_SERIES + 1)
        ]

        @app.callback(
            Output({"type": "cursor-readout", "index": _ro}, "style"),
            Output({"type": "cursor-readout-text", "index": _ro}, "children"),
            Input({"type": "cursor-ts", "index": _ro}, "data"),
            State("session-id", "data"),
            State("tag-nicknames", "data"),
            *_ro_series_states,
            prevent_initial_call=True,
        )
        def update_cursor_readout(cursor_ts, session_id, nn_data, *series_vals,
                                  _cid=_ro):
            if cursor_ts is None or not session_id:
                return {"display": "none"}, ""
            try:
                cursor_t = pd.Timestamp(cursor_ts)
            except Exception:
                return {"display": "none"}, ""

            meta = get_metadata(session_id)
            if not meta:
                return {"display": "none"}, ""
            df = query_full_data(session_id)
            tag_map = meta.get("tag_map", {})
            nn = nn_data or {}

            parts = [html.Span(
                f"Cursor: {cursor_t.strftime('%Y-%m-%d %H:%M:%S')}  ",
                style={"color": "#d2a8ff", "fontWeight": "bold"},
            )]
            for idx, tag_code in enumerate(series_vals):
                if not tag_code or tag_code not in df.columns:
                    continue
                color = TRACE_COLORS[idx % len(TRACE_COLORS)]
                info = tag_map.get(tag_code, {})
                tag_nn = nn.get(tag_code, {})
                name = tag_nn.get("nickname") or info.get("name", tag_code)
                units = tag_nn.get("unit") or info.get("units", "")
                decimals = info.get("decimals", 2)
                value = _interpolate_at(df, tag_code, cursor_t)
                if value is not None:
                    try:
                        val_str = f"{value:.{int(decimals)}f}"
                    except (ValueError, TypeError):
                        val_str = f"{value:.2f}"
                else:
                    val_str = "N/A"
                unit_str = f" {units}" if units else ""
                parts.append(html.Span(
                    f"  S{idx+1} {name}: {val_str}{unit_str}",
                    style={"color": color, "fontSize": "11px"},
                ))

            return {"display": "block"}, parts

        update_cursor_readout.__name__ = f"update_cursor_readout_{_ro}"
