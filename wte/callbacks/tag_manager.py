"""
Toggle tag panel, add custom units, populate tag rows, update nicknames,
refresh dropdown labels.
"""

from dash import ALL, dcc, html, Input, Output, State, callback_context, no_update

from wte.config import MAX_CHARTS, NUM_SERIES, num_or_none
from wte.styles import (
    TEXT_COLOR, ACCENT, GRID_COLOR, MUTED_TEXT,
    INPUT_STYLE, DROPDOWN_STYLE,
)
from wte.data.session import get_metadata
from wte.data.persistence import load_tag_manager_data, save_tag_manager_data
from wte.layout.tag_manager import UNIT_OPTIONS, BUILTIN_UNITS


def register(app):
    # --- Toggle tag panel ---
    @app.callback(
        Output("tag-panel", "style"),
        Output("tag-panel-toggle", "children"),
        Input("tag-panel-toggle", "n_clicks"),
        State("tag-panel", "style"),
        prevent_initial_call=True,
    )
    def toggle_tag_panel(n_clicks, current_style):
        if not n_clicks:
            return no_update, no_update
        is_hidden = current_style.get("display") == "none"
        new_style = {**current_style, "display": "block" if is_hidden else "none"}
        label = "Tag Manager \u25b2" if is_hidden else "Tag Manager \u25bc"
        return new_style, label

    # --- Add custom unit ---
    @app.callback(
        Output("custom-units", "data"),
        Output("custom-unit-input", "value"),
        Input("add-unit-btn", "n_clicks"),
        State("custom-unit-input", "value"),
        State("custom-units", "data"),
        prevent_initial_call=True,
    )
    def add_custom_unit(n_clicks, new_unit, custom_units):
        if not n_clicks:
            return no_update, no_update
        if custom_units is None:
            custom_units = []
        if not new_unit or not new_unit.strip():
            return no_update, no_update
        unit = new_unit.strip()
        if unit in BUILTIN_UNITS or unit in custom_units:
            return no_update, ""
        custom_units = custom_units + [unit]
        nicknames, _ = load_tag_manager_data()
        save_tag_manager_data(nicknames, custom_units)
        return custom_units, ""

    # --- Populate tag rows ---
    @app.callback(
        Output("tag-rows-container", "children"),
        Input("data-stats", "children"),
        Input("custom-units", "data"),
        State("tag-nicknames", "data"),
        State("session-id", "data"),
    )
    def populate_tag_rows(stats_text, custom_units, saved_nicknames, session_id):
        if not session_id:
            return html.Span("No tags loaded.", style={"color": MUTED_TEXT, "fontSize": "12px"})
        meta = get_metadata(session_id)
        if not meta:
            return html.Span("No tags loaded.", style={"color": MUTED_TEXT, "fontSize": "12px"})
        tag_map = meta.get("tag_map", {})
        all_tags = meta.get("all_tags", [])
        if not all_tags:
            return html.Span("No tags loaded.", style={"color": MUTED_TEXT, "fontSize": "12px"})

        if saved_nicknames is None:
            saved_nicknames = {}

        if custom_units:
            all_unit_options = UNIT_OPTIONS + [
                {"label": u, "value": u} for u in custom_units
            ]
        else:
            all_unit_options = UNIT_OPTIONS

        rows = []
        for tag_code in all_tags:
            info = tag_map.get(tag_code, {})
            current_name = info.get("name", tag_code)
            default_unit = info.get("units", "")
            saved = saved_nicknames.get(tag_code, {})
            saved_nick = saved.get("nickname", "")
            saved_unit = saved.get("unit", default_unit)
            saved_low = saved.get("y_low", info.get("y_low"))
            saved_high = saved.get("y_high", info.get("y_high"))
            row = html.Div(style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1.5fr 1fr 1fr 0.7fr 0.7fr",
                "gap": "6px",
                "padding": "3px 0",
                "alignItems": "center",
                "borderBottom": f"1px solid {GRID_COLOR}",
            }, children=[
                html.Span(tag_code, style={
                    "color": TEXT_COLOR, "fontSize": "11px",
                    "overflow": "hidden", "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                }, title=tag_code),
                html.Span(current_name, style={
                    "color": MUTED_TEXT, "fontSize": "11px",
                    "overflow": "hidden", "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                }, title=current_name),
                dcc.Input(
                    id={"type": "tag-nickname", "tag": tag_code},
                    type="text", value=saved_nick,
                    placeholder="Nickname...",
                    style={**INPUT_STYLE, "width": "100%", "fontSize": "11px"},
                    debounce=True,
                ),
                dcc.Dropdown(
                    id={"type": "tag-unit", "tag": tag_code},
                    options=all_unit_options,
                    value=saved_unit,
                    placeholder="Unit...",
                    clearable=True,
                    style={**DROPDOWN_STYLE, "width": "100%", "fontSize": "11px"},
                    className="dark-dropdown",
                ),
                dcc.Input(
                    id={"type": "tag-limit-low", "tag": tag_code},
                    type="number",
                    value=saved_low,
                    placeholder="Low...",
                    style={**INPUT_STYLE, "width": "100%", "fontSize": "11px"},
                    debounce=True,
                ),
                dcc.Input(
                    id={"type": "tag-limit-high", "tag": tag_code},
                    type="number",
                    value=saved_high,
                    placeholder="High...",
                    style={**INPUT_STYLE, "width": "100%", "fontSize": "11px"},
                    debounce=True,
                ),
            ])
            rows.append(row)
        return rows

    # --- Store nicknames/units ---
    @app.callback(
        Output("tag-nicknames", "data"),
        Input({"type": "tag-nickname", "tag": ALL}, "value"),
        Input({"type": "tag-unit", "tag": ALL}, "value"),
        Input({"type": "tag-limit-low", "tag": ALL}, "value"),
        Input({"type": "tag-limit-high", "tag": ALL}, "value"),
        State("tag-nicknames", "data"),
        prevent_initial_call=True,
    )
    def update_tag_nicknames(nicknames, units, limit_lows, limit_highs, current_data):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        if current_data is None:
            current_data = {}

        nick_inputs = ctx.inputs_list[0] if ctx.inputs_list else []
        unit_inputs = ctx.inputs_list[1] if len(ctx.inputs_list) > 1 else []
        low_inputs = ctx.inputs_list[2] if len(ctx.inputs_list) > 2 else []
        high_inputs = ctx.inputs_list[3] if len(ctx.inputs_list) > 3 else []

        for inp in nick_inputs:
            tag_code = inp["id"]["tag"]
            val = inp.get("value", "")
            if tag_code not in current_data:
                current_data[tag_code] = {}
            current_data[tag_code]["nickname"] = val or ""

        for inp in unit_inputs:
            tag_code = inp["id"]["tag"]
            val = inp.get("value", "")
            if tag_code not in current_data:
                current_data[tag_code] = {}
            current_data[tag_code]["unit"] = val or ""

        for inp in low_inputs:
            tag_code = inp["id"]["tag"]
            val = inp.get("value")
            if tag_code not in current_data:
                current_data[tag_code] = {}
            current_data[tag_code]["y_low"] = num_or_none(val)

        for inp in high_inputs:
            tag_code = inp["id"]["tag"]
            val = inp.get("value")
            if tag_code not in current_data:
                current_data[tag_code] = {}
            current_data[tag_code]["y_high"] = num_or_none(val)

        _, custom_units = load_tag_manager_data()
        save_tag_manager_data(current_data, custom_units)
        return current_data

    # --- Refresh dropdown labels ---
    _nickname_dd_outputs = []
    for _c in range(1, MAX_CHARTS + 1):
        for _s in range(1, NUM_SERIES + 1):
            _nickname_dd_outputs.append(
                Output({"type": "series-dd", "chart": _c, "series": _s}, "options", allow_duplicate=True)
            )

    @app.callback(
        _nickname_dd_outputs,
        Input("tag-nicknames", "data"),
        State("session-id", "data"),
        prevent_initial_call=True,
    )
    def update_dropdown_labels(nn_data, session_id):
        if not session_id:
            return [no_update] * len(_nickname_dd_outputs)
        meta = get_metadata(session_id)
        if not meta:
            return [no_update] * len(_nickname_dd_outputs)
        tag_map = meta.get("tag_map", {})
        all_tags = meta.get("all_tags", [])
        if not all_tags:
            return [no_update] * len(_nickname_dd_outputs)
        if nn_data is None:
            nn_data = {}

        tag_options = []
        for c in all_tags:
            info = tag_map.get(c, {})
            nn = nn_data.get(c, {})
            nickname = nn.get("nickname", "")
            unit_override = nn.get("unit", "")
            name = nickname if nickname else info.get("name", c)
            units = unit_override if unit_override else info.get("units", "")
            unit_str = f" [{units}]" if units else ""
            label = f"{c} - {name}{unit_str}"
            tag_options.append({"label": label, "value": c})

        return [tag_options] * len(_nickname_dd_outputs)
