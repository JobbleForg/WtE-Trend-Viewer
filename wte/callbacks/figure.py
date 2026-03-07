"""
build_figure(), _interpolate_at() - the chart rendering engine.
"""

from collections import OrderedDict

import pandas as pd
import plotly.graph_objects as go

from wte.styles import (
    CHART_BG, GRID_COLOR, TEXT_COLOR, MUTED_TEXT, TRACE_COLORS,
)


def _interpolate_at(df, column, timestamp):
    """Linearly interpolate a column value at the given timestamp."""
    if column not in df.columns or "Time" not in df.columns:
        return None
    sub = df[["Time", column]].dropna(subset=[column])
    if sub.empty:
        return None
    times = sub["Time"]
    ts = pd.Timestamp(timestamp)
    if ts <= times.iloc[0]:
        return float(sub[column].iloc[0])
    if ts >= times.iloc[-1]:
        return float(sub[column].iloc[-1])
    idx_after = times.searchsorted(ts)
    idx_before = idx_after - 1
    t0, t1 = times.iloc[idx_before], times.iloc[idx_after]
    v0, v1 = float(sub[column].iloc[idx_before]), float(sub[column].iloc[idx_after])
    if t1 == t0:
        return v0
    frac = (ts - t0).total_seconds() / (t1 - t0).total_seconds()
    return v0 + frac * (v1 - v0)


def _empty_figure(message="Load data to begin"):
    """Return an empty figure with a centred message."""
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(family="Consolas, monospace", size=11, color=TEXT_COLOR),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=message, showarrow=False,
                          font=dict(size=14, color=MUTED_TEXT),
                          xref="paper", yref="paper", x=0.5, y=0.5)],
    )
    return fig


def build_figure(df_slice, selected_tags, tag_map, x_revision=None,
                 nicknames=None, own_scale_flags=None, lock_scale_flags=None,
                 hide_limit_flags=None, show_limits=False, cursor_ts=None,
                 limit_overrides=None, ruler_y=None, ruler_time=None):
    """Build a Plotly figure with shared/own Y-axes, limits, rulers, cursor."""
    fig = go.Figure()
    if df_slice is None or df_slice.empty:
        return _empty_figure()

    if nicknames is None:
        nicknames = {}
    if own_scale_flags is None:
        own_scale_flags = [False] * len(selected_tags)
    if lock_scale_flags is None:
        lock_scale_flags = [False] * len(selected_tags)
    if hide_limit_flags is None:
        hide_limit_flags = [False] * len(selected_tags)
    if limit_overrides is None:
        limit_overrides = {}

    # --- Step 1: Gather info for every active series -----------------------
    active_series = []
    for idx, tag_code in enumerate(selected_tags):
        if not tag_code or tag_code not in df_slice.columns:
            continue
        info = tag_map.get(tag_code, {})
        name = info.get("name", tag_code)
        units = info.get("units", "")
        tag_nn = nicknames.get(tag_code, {})
        nickname = tag_nn.get("nickname", "")
        unit_override = tag_nn.get("unit", "")
        display_name = nickname if nickname else name
        display_unit = unit_override if unit_override else units
        color = TRACE_COLORS[idx % len(TRACE_COLORS)]
        active_series.append((idx, tag_code, display_name, display_unit, color, info))

    if not active_series:
        return _empty_figure("Select tags to display")

    # --- Step 2: Group series by effective unit ----------------------------
    unit_groups = OrderedDict()
    for s in active_series:
        slot_idx = s[0]
        is_own = own_scale_flags[slot_idx] if slot_idx < len(own_scale_flags) else False
        if is_own or not s[3]:
            unit_key = f"_own_{s[1]}"
        else:
            unit_key = s[3]
        if unit_key not in unit_groups:
            unit_groups[unit_key] = []
        unit_groups[unit_key].append(s)

    # --- Step 3: Assign one Y-axis per unit group, alternating L/R ---------
    unit_to_axis = {}
    active_axes = []
    for axis_idx, (unit_key, members) in enumerate(unit_groups.items()):
        axis_num = axis_idx + 1
        if axis_idx % 2 == 0:
            side, offset = "left", (axis_idx // 2) * 0.05
        else:
            side, offset = "right", (axis_idx // 2) * 0.05
        axis_color = members[0][4] if len(members) == 1 else TEXT_COLOR
        display_unit = members[0][3]
        series_tags = ", ".join(f"S{m[0] + 1}" for m in members)
        if len(members) == 1:
            name_part = members[0][2]
            label = f"{name_part} [{display_unit}]" if display_unit else name_part
        else:
            label = f"{series_tags} [{display_unit}]" if display_unit else series_tags
        is_locked = any(
            lock_scale_flags[m[0]] if m[0] < len(lock_scale_flags) else False
            for m in members
        )
        unit_to_axis[unit_key] = axis_num
        active_axes.append({
            "num": axis_num, "side": side, "offset": offset,
            "color": axis_color, "label": label,
            "unit_key": unit_key, "locked": is_locked,
        })

    # --- Step 4: Add traces ------------------------------------------------
    for (idx, tag_code, display_name, display_unit, color, info) in active_series:
        is_own = own_scale_flags[idx] if idx < len(own_scale_flags) else False
        if is_own or not display_unit:
            unit_key = f"_own_{tag_code}"
        else:
            unit_key = display_unit
        axis_num = unit_to_axis[unit_key]
        yaxis_key = "y" if axis_num == 1 else f"y{axis_num}"
        trace_label = f"{display_name} [{display_unit}]" if display_unit else display_name
        fig.add_trace(go.Scattergl(
            x=df_slice["Time"], y=df_slice[tag_code],
            name=trace_label, yaxis=yaxis_key,
            line=dict(color=color, width=1.5), mode="lines",
        ))

    # --- Step 4b: Threshold limit lines ------------------------------------
    limit_shapes = []
    limit_annotations = []
    alarm_axes = {}
    if show_limits:
        for (idx, tag_code, display_name, display_unit, color, info) in active_series:
            is_hidden = hide_limit_flags[idx] if idx < len(hide_limit_flags) else False
            if is_hidden:
                continue
            ovr = limit_overrides.get(tag_code, {})
            y_high = ovr.get("y_high", info.get("y_high"))
            y_low = ovr.get("y_low", info.get("y_low"))
            if y_high is None and y_low is None:
                continue
            is_own = own_scale_flags[idx] if idx < len(own_scale_flags) else False
            if is_own or not display_unit:
                unit_key = f"_own_{tag_code}"
            else:
                unit_key = display_unit
            axis_num = unit_to_axis[unit_key]
            yref = "y" if axis_num == 1 else f"y{axis_num}"
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            line_color = f"rgba({r},{g},{b},0.45)"

            if tag_code in df_slice.columns and not df_slice.empty:
                series_data = df_slice[tag_code].dropna()
                if y_high is not None and (series_data > y_high).any():
                    alarm_axes[axis_num] = True
                if y_low is not None and (series_data < y_low).any():
                    alarm_axes[axis_num] = True

            for val, label_suffix in [(y_high, "Hi"), (y_low, "Lo")]:
                if val is None:
                    continue
                limit_shapes.append(dict(
                    type="line", xref="paper", x0=0, x1=1,
                    yref=yref, y0=val, y1=val,
                    line=dict(color=line_color, width=1.2, dash="dash"),
                    layer="above",
                ))
                limit_annotations.append(dict(
                    text=f"S{idx+1} {label_suffix}: {val}",
                    xref="paper", x=1.0, yref=yref, y=val,
                    xanchor="left", showarrow=False,
                    font=dict(size=9, color=line_color),
                    bgcolor="rgba(13,17,23,0.7)",
                ))

    # --- Step 4c: Cursor vertical line -------------------------------------
    if cursor_ts:
        try:
            ct = pd.Timestamp(cursor_ts)
            limit_shapes.append(dict(
                type="line", yref="paper", y0=0, y1=1,
                xref="x", x0=ct, x1=ct,
                line=dict(color="#d2a8ff", width=1.5, dash="dashdot"),
                layer="above",
            ))
        except Exception:
            pass

    # --- Step 4d: Horizontal ruler -----------------------------------------
    if ruler_y is not None:
        try:
            ry = float(ruler_y)
            limit_shapes.append(dict(
                type="line", xref="paper", x0=0, x1=1,
                yref="y", y0=ry, y1=ry,
                line=dict(color="#f0b832", width=1.5, dash="dash"),
                layer="above",
            ))
            fig.add_annotation(
                xref="paper", x=1.0, yref="y", y=ry,
                text=f"  {ry:g}", showarrow=False,
                font=dict(color="#f0b832", size=10),
                xanchor="left",
            )
        except (ValueError, TypeError):
            pass

    # --- Step 4e: Vertical ruler -------------------------------------------
    if ruler_time is not None:
        try:
            rt = pd.Timestamp(ruler_time)
            limit_shapes.append(dict(
                type="line", xref="x", x0=rt, x1=rt,
                yref="paper", y0=0, y1=1,
                line=dict(color="#58a6ff", width=1.5, dash="dash"),
                layer="above",
            ))
            fig.add_annotation(
                xref="x", x=rt, yref="paper", y=1.0,
                text=rt.strftime("  %H:%M:%S"), showarrow=False,
                font=dict(color="#58a6ff", size=10),
                yanchor="bottom", xanchor="left",
            )
            for (idx, tag_code, display_name, display_unit, color, info) in active_series:
                val = _interpolate_at(df_slice, tag_code, rt)
                if val is not None and not pd.isna(val):
                    is_own = own_scale_flags[idx] if idx < len(own_scale_flags) else False
                    if is_own or not display_unit:
                        ukey = f"_own_{tag_code}"
                    else:
                        ukey = display_unit
                    ax_num = unit_to_axis[ukey]
                    yref = "y" if ax_num == 1 else f"y{ax_num}"
                    fig.add_annotation(
                        xref="x", x=rt, yref=yref, y=val,
                        text=f" {val:g}", showarrow=False,
                        font=dict(color=color, size=9),
                        xanchor="left", bgcolor="rgba(0,0,0,0.6)",
                    )
        except Exception:
            pass

    # --- Step 5: Build Y-axis layout dicts ---------------------------------
    max_left = max((a["offset"] for a in active_axes if a["side"] == "left"), default=0)
    max_right = max((a["offset"] for a in active_axes if a["side"] == "right"), default=0)
    x_domain = [max_left, 1.0 - max_right]

    yaxis_layouts = {}
    for ax in active_axes:
        key = "yaxis" if ax["num"] == 1 else f"yaxis{ax['num']}"
        if ax["side"] == "left":
            position = max_left - ax["offset"]
        else:
            position = (1.0 - max_right) + ax["offset"]
        axis_label = ax["label"]
        axis_color = ax["color"]
        if alarm_axes.get(ax["num"]):
            axis_label = "\u26A0 " + axis_label
            axis_color = "#f85149"
        layout = dict(
            title=dict(text=axis_label, font=dict(color=axis_color, size=10)),
            tickfont=dict(color=ax["color"], size=9),
            gridcolor=GRID_COLOR if ax["num"] == 1 else "rgba(0,0,0,0)",
            showgrid=(ax["num"] == 1), zeroline=False, side=ax["side"],
            uirevision=ax["unit_key"],
            fixedrange=ax.get("locked", False),
        )
        if ax["num"] > 1:
            layout["overlaying"] = "y"
            layout["position"] = position
            layout["anchor"] = "free"
        yaxis_layouts[key] = layout

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(family="Consolas, monospace", size=11, color=TEXT_COLOR),
        margin=dict(l=45 if max_left > 0 else 10,
                    r=45 if max_right > 0 else 10, t=10, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=10)),
        xaxis=dict(gridcolor=GRID_COLOR, showgrid=True, zeroline=False,
                   tickformat="%H:%M\n%d-%b", domain=x_domain,
                   uirevision=x_revision),
        uirevision="keep",
        hovermode="x unified",
        shapes=limit_shapes,
        annotations=limit_annotations,
        **yaxis_layouts,
    )
    return fig
