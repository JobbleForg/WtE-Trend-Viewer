"""
Notes overlay: toggle, load from localStorage, save to localStorage.
"""

from dash import Input, Output, State, callback_context, no_update


def register(app):
    @app.callback(
        Output("notes-overlay", "style"),
        Input("notes-toggle-btn", "n_clicks"),
        Input("notes-close-btn", "n_clicks"),
        State("notes-overlay", "style"),
        prevent_initial_call=True,
    )
    def toggle_notes(toggle_clicks, close_clicks, current_style):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        is_hidden = (current_style or {}).get("display") == "none"
        if "notes-close-btn" in ctx.triggered[0]["prop_id"]:
            return {**current_style, "display": "none"}
        return {**current_style, "display": "flex" if is_hidden else "none"}

    @app.callback(
        Output("notes-textarea", "value"),
        Input("notes-text", "data"),
    )
    def load_notes(saved_text):
        return saved_text or ""

    @app.callback(
        Output("notes-text", "data"),
        Input("notes-textarea", "value"),
        prevent_initial_call=True,
    )
    def save_notes(text):
        return text or ""
