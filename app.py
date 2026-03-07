"""
Entry point: creates Dash app, builds layout, registers callbacks, runs server.
"""

from wte import create_app

app = create_app()

if __name__ == "__main__":
    print("Starting WtE Trend Viewer...")
    print("Open http://localhost:8050 and load an Excel file to begin.")
    app.run(debug=False, port=8050)
