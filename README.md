# WtE-Trend-Viewer
Grabs excel data which can be viewed in the browser dashboard.

## What's New in v0.2.0

**10 series per chart with shared Y-axes** — Each chart now supports 10 series (up from 6). Tags that share the same unit are automatically grouped onto a single Y-axis, keeping the chart readable. The axis label shows which series share it (e.g. "S2, S4, S7 [°C]"). Each series has an "Own" checkbox to force it onto an independent axis when needed.

**Scale locking** — A per-series lock button prevents accidental zoom or pan on individual Y-axes. Useful when you've set a reference scale and want to keep it fixed while exploring other signals.

**Rolling mean filter** — Each series slot has a filter input field. Set a window size (number of data points) to apply a centered rolling mean, smoothing noisy signals without losing edge data.

**Save/Load updated** — Saved setups now include own-scale flags, lock-scale flags, and filter window values. Old saved setups load with sensible defaults (shared axes, unlocked, no filter).

## Running from WSL (Linux)

### First-time setup

```bash
# Clone the repository
git clone https://github.com/JobbleForg/WtE-Trend-Viewer.git
cd WtE-Trend-Viewer

# Create a virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install dash plotly pandas openpyxl
```

### Download the latest version

If you already have the repository cloned, pull the newest changes:

```bash
cd WtE-Trend-Viewer
git pull origin main
```

### Start the server

```bash
source venv/bin/activate
python trend_viewer.py
```

Then open your browser and go to **http://localhost:8050**

Click **Load File** to upload an Excel data file. If your file is on the Windows side, you can find it at:
```
/mnt/c/Users/<YourUsername>/path/to/file.xlsx
```

### Stop the server

Press **Ctrl+C** in the terminal where the server is running.
