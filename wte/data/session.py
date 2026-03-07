"""
SQLite session helpers: create_session_db, get_metadata, query_time_slice,
query_full_data, cleanup_session_db.
"""

import json
import os
import sqlite3
import tempfile

import pandas as pd


def _db_path(session_id):
    """Return the SQLite database file path for a session."""
    return os.path.join(tempfile.gettempdir(), f"wte_session_{session_id}.db")


def create_session_db(session_id, df, tag_map, chart_packages, all_tags,
                      name_to_code, data_start, data_end):
    """Create a SQLite database for a session and store all data."""
    db = _db_path(session_id)
    conn = sqlite3.connect(db)
    df.to_sql("data", conn, if_exists="replace", index=False)
    meta = {
        "tag_map": tag_map,
        "chart_packages": chart_packages,
        "all_tags": all_tags,
        "name_to_code": name_to_code,
        "data_start": data_start.isoformat(),
        "data_end": data_end.isoformat(),
    }
    conn.execute(
        "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("session_meta", json.dumps(meta)),
    )
    conn.commit()
    conn.close()


def get_metadata(session_id):
    """Retrieve session metadata from SQLite.  Returns dict or None."""
    db = _db_path(session_id)
    if not os.path.exists(db):
        return None
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key='session_meta'"
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def query_time_slice(session_id, start_time, end_time, columns=None):
    """Query the data table for a time range.  Returns a DataFrame."""
    db = _db_path(session_id)
    if not os.path.exists(db):
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        if columns:
            safe_cols = [c for c in columns if c]
            col_list = ", ".join(f'"{c}"' for c in ["Time"] + safe_cols)
            query = (
                f"SELECT {col_list} FROM data "
                f"WHERE Time >= ? AND Time <= ? ORDER BY Time"
            )
        else:
            query = (
                "SELECT * FROM data WHERE Time >= ? AND Time <= ? ORDER BY Time"
            )
        df = pd.read_sql_query(
            query, conn,
            params=[start_time.isoformat(), end_time.isoformat()],
        )
        if "Time" in df.columns:
            df["Time"] = pd.to_datetime(df["Time"])
        return df
    finally:
        conn.close()


def query_full_data(session_id):
    """Query the full data table.  Returns a DataFrame."""
    db = _db_path(session_id)
    if not os.path.exists(db):
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query("SELECT * FROM data ORDER BY Time", conn)
        if "Time" in df.columns:
            df["Time"] = pd.to_datetime(df["Time"])
        return df
    finally:
        conn.close()


def cleanup_session_db(session_id):
    """Remove the SQLite database file for a session."""
    db = _db_path(session_id)
    try:
        os.remove(db)
    except OSError:
        pass
