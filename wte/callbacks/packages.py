"""
Chart package loading from Tag Refs.
"""

from dash import Input, Output, State, no_update

from wte.config import NUM_SERIES
from wte.data.session import get_metadata


def register(app):
    _pkg_outputs = [
        Output({"type": "series-dd", "chart": 1, "series": s}, "value", allow_duplicate=True)
        for s in range(1, NUM_SERIES + 1)
    ]

    @app.callback(
        _pkg_outputs,
        Input("pkg-select", "value"),
        State("session-id", "data"),
        prevent_initial_call=True,
    )
    def load_chart_package(pkg_num, session_id):
        if not pkg_num:
            return [no_update] * NUM_SERIES
        if not session_id:
            return [no_update] * NUM_SERIES
        meta = get_metadata(session_id)
        if not meta:
            return [no_update] * NUM_SERIES
        name_to_code = meta["name_to_code"]
        all_tags = meta["all_tags"]
        for pkg in meta["chart_packages"]:
            if pkg["num"] == pkg_num:
                codes = []
                for n in pkg["tags"]:
                    if not n:
                        codes.append(None)
                    elif n in name_to_code:
                        codes.append(name_to_code[n])
                    elif n in all_tags:
                        codes.append(n)
                    else:
                        codes.append(None)
                while len(codes) < NUM_SERIES:
                    codes.append(None)
                return codes[:NUM_SERIES]
        return [no_update] * NUM_SERIES
