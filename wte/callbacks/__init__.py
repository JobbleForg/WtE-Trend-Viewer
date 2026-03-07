"""
Callback registration hub.
Imports and registers all callback modules against the Dash app.
"""

from wte.callbacks import (
    visibility,
    file_io,
    chart_update,
    sync,
    notes,
    tag_manager,
    packages,
    setups,
    chart_tools,
    session_restore,
)


def register_all(app):
    """Register every callback module with the given Dash app."""
    visibility.register(app)
    file_io.register(app)
    chart_update.register(app)
    sync.register(app)
    notes.register(app)
    tag_manager.register(app)
    packages.register(app)
    setups.register(app)
    chart_tools.register(app)
    session_restore.register(app)
