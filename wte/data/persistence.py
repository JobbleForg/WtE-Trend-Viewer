"""
Tag manager JSON read/write, temp file cleanup, upload persistence.
"""

import atexit
import glob
import json
import os
import shutil
import tempfile

from wte.config import TAG_DATA_FILE, LAST_SESSION_DIR


# ---------------------------------------------------------------------------
# Temp-file cleanup (Issue #3)
# ---------------------------------------------------------------------------

def _cleanup_temp_files():
    """Remove any leftover wte_upload_* temp files on shutdown."""
    pattern = os.path.join(tempfile.gettempdir(), "wte_upload_*")
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass
    db_pattern = os.path.join(tempfile.gettempdir(), "wte_session_*.db")
    for path in glob.glob(db_pattern):
        try:
            os.remove(path)
        except OSError:
            pass


atexit.register(_cleanup_temp_files)


# ---------------------------------------------------------------------------
# Persistent tag-manager data (survives reboots / updates)
# ---------------------------------------------------------------------------

def load_tag_manager_data():
    """Load saved tag nicknames and custom units from the local JSON file."""
    if os.path.isfile(TAG_DATA_FILE):
        try:
            with open(TAG_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("nicknames", {}), data.get("custom_units", [])
        except (json.JSONDecodeError, OSError):
            return {}, []
    return {}, []


def save_tag_manager_data(nicknames, custom_units):
    """Write tag nicknames and custom units to the local JSON file."""
    payload = {"nicknames": nicknames or {}, "custom_units": custom_units or []}
    try:
        with open(TAG_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def persist_upload(src_path, filename):
    """Copy the uploaded file to _last_session/ for autoload on next startup."""
    os.makedirs(LAST_SESSION_DIR, exist_ok=True)
    dst = os.path.join(LAST_SESSION_DIR, filename)
    try:
        shutil.copy2(src_path, dst)
    except OSError:
        pass
    return dst


# Pre-load persisted data so stores can be initialised with it
INIT_NICKNAMES, INIT_CUSTOM_UNITS = load_tag_manager_data()
