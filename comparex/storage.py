"""SQLite comparison history."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def save_comparison(path: str | Path, products: list[dict], verdict: str) -> int:
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS comparisons (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, products_json TEXT NOT NULL, verdict TEXT NOT NULL)")
        cur = con.execute("INSERT INTO comparisons(created_at, products_json, verdict) VALUES (?, ?, ?)", (datetime.now(timezone.utc).isoformat(), json.dumps(products), verdict))
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()

def recent_comparisons(path: str | Path, limit: int = 20) -> list[dict]:
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS comparisons (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, products_json TEXT NOT NULL, verdict TEXT NOT NULL)")
        rows = con.execute("SELECT id, created_at, products_json, verdict FROM comparisons ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "created_at": r[1], "products": json.loads(r[2]), "verdict": r[3]} for r in rows]
    finally:
        con.close()
