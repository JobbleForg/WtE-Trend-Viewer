# WtE-Trend-Viewer
Grabs excel data which can be viewed in the browser dashboard.

## Running from WSL (Linux)

### First-time setup

```bash
# Clone the repository
git clone https://github.com/JobbleForg/WtE-Trend-Viewer.git
cd WtE-Trend-Viewer

# Install dependencies
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
python trend_viewer.py
```

Then open your browser and go to **http://localhost:8050**

Click **Load File** to upload an Excel data file. If your file is on the Windows side, you can find it at:
```
/mnt/c/Users/<YourUsername>/path/to/file.xlsx
```

### Stop the server

Press **Ctrl+C** in the terminal where the server is running.
