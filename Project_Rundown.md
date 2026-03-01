# Waste-to-Energy Plant Trend Viewer — Project Rundown

## Overview

This project is a Python web application for viewing power plant process data. It mimics DCS (Distributed Control System) trend displays like those found in ABB 800xA, allowing an engineer to quickly load, view, scroll, and compare tagged process variables from historical datasets.

The system is built for **quick deployment and disposal** — upload a dataset, analyze it, discard it, and repeat with the next one. No database, no persistent connections, no complex infrastructure. One Python file, one browser tab.

**Stack:** Python, Dash, Plotly, Pandas

---

## File Structure

| File | Purpose |
|------|---------|
| `trend_viewer.py` | The entire application — server, layout, callbacks, data loading |
| `README.md` | Setup and run instructions for WSL/Linux |
| `Project_Rundown.md` | This document |
| `.gitignore` | Excludes Excel files, `__pycache__/`, `.claude/` |

No Excel data files are committed. Users upload their own via the browser interface.

---

## Architecture

### Single-File Design

Everything lives in `trend_viewer.py`. There are no separate modules, no config files, no build step. This is deliberate — the tool is meant to be cloned and run in under a minute. A single file keeps deployment trivial and makes the entire system greppable.

### Data Flow

```
Excel file (user upload)
    |
    v
Temp file on disk (cleaned up on next upload or server shutdown)
    |
    v
Pandas DataFrame (parsed, timestamped, sorted)
    |
    v
dcc.Store (JSON in browser session memory)
    |
    v
Plotly figures (rendered per chart on each callback)
```

The DataFrame is serialized to JSON and stored in the browser via Dash's `dcc.Store` component. Each callback that needs the data deserializes it on the fly. This means:
- No global state on the server
- Multiple users can load different files simultaneously
- Server restarts don't corrupt anyone's session

### No Global State

Early versions stored the DataFrame and tag metadata in a Python global variable. This was replaced with per-session browser storage (Issue #4) to prevent data leakage between users if the server is shared. All mutable state now lives in `dcc.Store` components in the client's browser.

---

## Layout

### Header Toolbar

A single horizontal bar at the top containing all global controls:

| Control | Purpose |
|---------|---------|
| **Load File** | Upload button accepting `.xlsx`, `.xls`, `.xlsm` |
| **File name** | Displays the currently loaded filename |
| **Sheet** dropdown | Select which sheet to load from a multi-sheet workbook |
| **Package** dropdown | Quick-load predefined tag combinations from the Tag Refs sheet |
| **+ Add Chart** | Add a new chart panel (up to 8 total) |
| **Setup: Save/Load/Delete** | Persist and restore chart configurations via browser localStorage |

### Chart Panels

The main area is a flexbox grid of chart panels. Each panel is independent and contains:

**Title bar:** Chart number, width selector (Quarter/Half/Full), height selector (Small/Medium/Large/XL), Sync button, Close button.

**Graph:** A Plotly `Scattergl` line chart with up to 6 independent Y-axes, dark theme, unified hover mode.

**Series dropdowns:** Two rows of 3 dropdowns each (S1–S6), color-coded to match their trace. Each dropdown lists all tags from the loaded data.

**Time controls:** Go-to date/time inputs, window duration (minutes + hours), step size, scroll left/right buttons, and a Load Area button.

### Tag Manager

A collapsible panel at the bottom of the page. Allows per-tag customization:

| Column | Purpose |
|--------|---------|
| Tag Code | The raw column header from the Excel file |
| Current Name | The friendly name from the Tag Refs sheet (if available) |
| Nickname | User-editable override for the display name |
| Unit | Dropdown with common units, plus custom unit support |

The header row includes an "Add unit" input for defining custom units that aren't in the built-in list.

---

## Sections of `trend_viewer.py`

The file is organized into sequential sections, each separated by comment banners.

### Constants and Helpers (lines 1–60)

- `NUM_SERIES = 6` — traces per chart
- `MAX_CHARTS = 8` — pre-allocated chart slots
- `INITIAL_VISIBLE = 4` — charts shown on first load
- `_cleanup_temp_files()` — atexit handler for temp file cleanup
- `_num_or_none()` — safe numeric parser for Tag Refs values

### Data Loading (lines 62–137)

- `load_sheet_data(filepath, sheet_name)` — reads a sheet into a DataFrame, renames the first column to "Time", parses timestamps, drops invalid rows, sorts by time
- `try_load_tag_refs(filepath)` — attempts to read a "Tag Refs" sheet from the same workbook. Parses tag metadata (friendly names, units, decimals, Y-axis defaults) and chart package definitions. Returns empty dicts if the sheet doesn't exist — the app works fine without it.
- `tag_label(code, tag_map)` — formats a tag for dropdown display: `"AT1102 - Ln1_O2_A [%]"`

### Styling (lines 140–184)

All visual constants in one place. Dark theme inspired by GitHub's dark mode:

- Background: `#0d1117`
- Panel: `#161b22`
- Text: `#c9d1d9`
- Accent: `#58a6ff`
- Trace colors: blue, green, orange, purple, pink, light blue

Reusable style dicts: `LABEL_STYLE`, `INPUT_STYLE`, `DROPDOWN_STYLE`, `BTN_STYLE`.

### Layout Construction (lines 190–498)

- `make_chart_panel(chart_id)` — builds a single chart panel with all its controls. Called 8 times at layout creation. Hidden panels are pre-rendered with `display: none` and toggled via callbacks.
- `app.layout` — the root layout containing all stores, the header toolbar, the chart grid, and the Tag Manager.
- `app.index_string` — custom HTML template injecting dark-theme CSS for Dash's dropdown components.

### Callbacks

Callbacks are the reactive core of the app. Each one is triggered by user interactions and updates specific parts of the UI.

#### Visibility Management (lines 556–634)

- `update_visible_charts` — handles "+ Add Chart" and close button clicks. Updates the `visible-charts` store. Resets sync state if the master chart is closed.
- `update_panel_style` (per chart) — translates the visibility list and width/height selections into CSS styles.
- `update_graph_height` (per chart) — sets graph container height from the height dropdown.

#### File Upload and Sheet Loading (lines 637–767)

- `on_file_upload` — decodes the base64 upload, writes to a temp file, reads sheet names, cleans up the previous temp file.
- `on_sheet_selected` — loads the selected sheet into a DataFrame, parses Tag Refs, builds the session data payload, populates all dropdowns with tag options, initializes time controls to the data start.

#### Figure Builder (lines 774–878)

`_build_figure(df_slice, selected_tags, tag_map, x_revision, nicknames)` — the central rendering function. Takes a time-filtered DataFrame slice and builds a Plotly figure with:
- Up to 6 traces using `Scattergl` (WebGL-accelerated for performance)
- Independent Y-axes with configurable sides (alternating left/right)
- Axis position offsets to prevent overlap (0.0, 0.05, 0.10)
- `uirevision` per axis to preserve user zoom across callback updates
- Nickname and unit overrides from the Tag Manager

#### Chart Update (lines 885–965)

One callback per chart slot (8 total, registered in a for-loop). Triggered by:
- Series dropdown changes
- Go-to date/time input
- Window duration changes
- Scroll button clicks
- Tag nickname changes

The callback reads the session data from `dcc.Store`, deserializes the DataFrame, computes the time window, filters the data, and calls `_build_figure`.

Scroll logic: left subtracts step minutes from start time, right adds. Clamped to data bounds.

#### Sync System (lines 968–1161)

Time synchronization lets one "master" chart control all others' time windows.

- `toggle_sync` — clicking Sync on a chart makes it the master. Clicking again (on the master only) deactivates sync. Locked charts ignore clicks.
- `propagate_sync` (per chart) — when the master's time controls change, propagates start time, go-to fields, window, and step to all other visible charts.
- `update_sync_border` (per chart) — the master gets a cyan border. Others remain default.
- `update_sync_btn` (per chart) — master shows "Unsync" (highlighted), locked charts show a lock icon, unsynced charts show the normal "Sync" button.
- `toggle_controls` (per chart) — disables time controls and Load Area on locked charts.

#### Zoom Sync (lines 1164–1261)

When sync is active and the user zooms/pans the master chart, `sync_zoom_from_master` reads the master's `relayoutData`, extracts the new X-axis range, computes the equivalent window duration, and pushes it to all synced charts.

#### Tag Manager (lines 1264–1436)

- `toggle_tag_panel` — shows/hides the panel.
- `add_custom_unit` — validates and stores user-defined units in a session store. Deduplicates against both built-in and previously added custom units.
- `populate_tag_rows` — rebuilds the tag table whenever data loads or custom units change. Merges built-in and custom unit options. Preserves existing nickname/unit selections from the session store.
- `update_tag_nicknames` — persists nickname and unit edits using pattern-matching callback IDs (`{"type": "tag-nickname", "tag": ALL}`).

#### Chart Packages (lines 1439–1477)

`load_chart_package` — when the user selects a package from the dropdown, resolves tag names to codes (via the `name_to_code` mapping from Tag Refs) and sets Chart 1's series dropdowns.

#### Save/Load Setups (lines 1480–1635)

Persistent chart configurations stored in the browser's localStorage:
- `save_setup` — captures all 8 charts' series selections, widths, heights, and the visible chart list. Stores under a user-provided name.
- `load_setup` — restores a saved configuration.
- `delete_setup` — removes a saved setup.
- `update_setup_dropdown` — refreshes the load dropdown whenever the store changes.

#### Load Area (lines 1638–1700)

Two callback groups:
- `track_x_range` (per chart) — listens to `relayoutData` and stores the current visible X-axis range.
- `load_area` (per chart) — when the Load Area button is clicked, reads the stored range, computes the matching time window, and updates the chart's time controls. This lets users zoom out to see a wider picture, then click Load Area to fetch data for the full visible range.

---

## Design Decisions

| Decision | Reasoning |
|----------|-----------|
| Single Python file | Clone-and-run simplicity. No build tools, no module resolution, no package structure to navigate. |
| Dash + Plotly | Interactive charts with zero JavaScript. Plotly's `Scattergl` handles 23k+ data points smoothly via WebGL. |
| Session-based storage | No global Python state. Multiple users can load different datasets without interference. |
| Pre-allocated chart panels | All 8 panels exist in the DOM from startup, toggled via CSS. Avoids dynamic component creation, which is complex in Dash. |
| Per-axis `uirevision` | Plotly resets zoom on figure updates by default. Setting `uirevision` to the tag code preserves user zoom unless the tag itself changes. |
| Temp file cleanup on upload | Each new upload deletes the previous temp file. An `atexit` handler catches any remaining files on shutdown. |
| Tag Refs are optional | The app works with any Excel file. If a "Tag Refs" sheet exists, it provides friendly names, units, and defaults. If not, raw column headers are used. |
| `allow_duplicate=True` | Multiple callbacks target the same outputs (e.g., `start-time` is written by scroll, sync, zoom sync, load area, and sheet load). Dash requires this flag to allow it. |
| Callback-per-chart in for-loops | Dash doesn't support truly dynamic callbacks. Registering 8 callbacks in a loop with default arguments (`_cid=_i`) is the standard pattern. |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `dash` | 2.x | Web framework, reactive callbacks, layout components |
| `plotly` | 5.x | Charting library (`Scattergl` for WebGL-accelerated line charts) |
| `pandas` | 2.x | DataFrame operations, Excel file reading, timestamp handling |
| `openpyxl` | 3.x | Excel `.xlsx` file engine for pandas |

Install: `pip install dash plotly pandas openpyxl`

---

## Running

```bash
python trend_viewer.py
```

Open `http://localhost:8050` in a browser. Click **Load File** to upload an Excel workbook. Select a data sheet. The charts populate with available tags.

See `README.md` for full WSL/Linux setup instructions including virtual environment configuration.
