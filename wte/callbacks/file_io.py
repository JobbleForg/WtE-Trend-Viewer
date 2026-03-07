"""
File upload callback, sheet selection -> data loading callback.
"""

import base64
import os
import tempfile
import uuid

import pandas as pd
from dash import Input, Output, State, no_update

from wte.config import MAX_CHARTS, NUM_SERIES
from wte.data.loader import load_sheet_data, try_load_tag_refs, tag_label
from wte.data.session import create_session_db
from wte.data.persistence import persist_upload


def register(app):
    # --- File upload ---
    @app.callback(
        Output("sheet-select", "options"),
        Output("sheet-select", "value"),
        Output("temp-file-path", "data"),
        Output("file-name-display", "children"),
        Input("file-upload", "contents"),
        State("file-upload", "filename"),
        State("temp-file-path", "data"),
        prevent_initial_call=True,
    )
    def on_file_upload(contents, filename, old_temp_path):
        if contents is None:
            return no_update, no_update, no_update, no_update
        if old_temp_path:
            try:
                os.remove(old_temp_path)
            except OSError:
                pass
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        tmp = tempfile.NamedTemporaryFile(
            prefix="wte_upload_", suffix=f"_{filename}", delete=False
        )
        temp_path = tmp.name
        try:
            tmp.write(decoded)
            tmp.close()
            xl = pd.ExcelFile(temp_path, engine="openpyxl")
            sheets = xl.sheet_names
            xl.close()
        except Exception as e:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return [], None, None, f"Error: {e}"
        options = [{"label": s, "value": s} for s in sheets]
        persist_upload(temp_path, filename)
        return options, None, temp_path, filename

    # --- Sheet selected -> load data ---
    _load_outputs = [
        Output("session-id", "data"),
        Output("data-stats", "children"),
        Output("pkg-select", "options"),
    ]
    for _c in range(1, MAX_CHARTS + 1):
        for _s in range(1, NUM_SERIES + 1):
            _load_outputs.append(Output({"type": "series-dd", "chart": _c, "series": _s}, "options", allow_duplicate=True))
            _load_outputs.append(Output({"type": "series-dd", "chart": _c, "series": _s}, "value", allow_duplicate=True))
        _load_outputs.append(Output({"type": "start-time", "index": _c}, "data", allow_duplicate=True))
        _load_outputs.append(Output({"type": "goto-date", "index": _c}, "value", allow_duplicate=True))

    @app.callback(
        _load_outputs,
        Input("sheet-select", "value"),
        State("temp-file-path", "data"),
        prevent_initial_call=True,
    )
    def on_sheet_selected(sheet_name, temp_path):
        if not sheet_name or not temp_path:
            return [no_update] * len(_load_outputs)
        try:
            df = load_sheet_data(temp_path, sheet_name)
            tag_map, chart_packages = try_load_tag_refs(temp_path)
        except Exception as e:
            results = [no_update, f"Error loading sheet: {e}"]
            results.extend([no_update] * (len(_load_outputs) - 2))
            return results

        if len(df) == 0 or "Time" not in df.columns:
            results = [no_update, "No timestamp data found in this sheet."]
            results.extend([no_update] * (len(_load_outputs) - 2))
            return results

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
            f"Tags: {len(all_tags)}"
        )

        tag_options = [{"label": tag_label(c, tag_map), "value": c} for c in all_tags]
        pkg_options = [{"label": "-- None --", "value": ""}]
        for pkg in chart_packages:
            names = [n for n in pkg["tags"] if n]
            pkg_options.append({
                "label": f"Pkg {pkg['num']}: {' / '.join(names)}",
                "value": pkg["num"],
            })

        results = [session_id, stats, pkg_options]
        start_iso = data_start.isoformat()
        date_str = data_start.strftime("%Y-%m-%d")
        for _c in range(1, MAX_CHARTS + 1):
            for _s in range(1, NUM_SERIES + 1):
                results.append(tag_options)
                results.append(None)
            results.append(start_iso)
            results.append(date_str)
        return results
