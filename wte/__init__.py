"""
WtE Trend Viewer package.

Creates the Dash app, assembles the layout, and registers all callbacks.
Import `app` from this module.
"""

from dash import Dash

from wte.layout import build_layout, get_index_string
from wte.callbacks import register_all


def create_app():
    """Factory function: build and return a fully configured Dash app."""
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = "WtE Trend Viewer"
    app.layout = build_layout()
    app.index_string = get_index_string()
    register_all(app)
    return app
