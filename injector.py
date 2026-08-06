"""9Router SQLite injector — masukkan harvested keys ke 9Router database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

NINE_ROUTER_DB_PATHS = [
    Path.home() / ".9router" / "db" / "data.sqlite",
    Path.home() / "9router" / "db" / "data.sqlite",
    Path("D:/9router/db/data.sqlite"),
    Path("D:/9router/data.sqlite"),
]

PROVIDER = "blackbox"
AUTH_TYPE = "apikey"  # 9Router uses "apikey" not "api_key"
BASE_URL = "https://api.blackbox.ai/v1"


def find_9router_db() -> Path | None:
    for p in NINE_ROUTER_DB_PATHS:
        if p.exists():
            return p
    return None


def inject_keys(keys_path: str = "output/keys.txt", db_path: str | None = None) -> int:
    db = Path(db_path) if db_path else find_9router_db()
    if db is None:
        raise FileNotFoundError("9Router database not found. Pass --db-path or install 9router first.")

    keys_file = Path(keys_path)
    if not keys_file.exists():
        raise FileNotFoundError(f"Keys file not found: {keys_path}")

    lines = [l.strip() for l in keys_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return 0

    conn = sqlite3.connect(str(db))
    cursor = conn.cursor()
    injected = 0

    for line in lines:
        parts = line.split(":")
        if len(parts) < 3:
            continue

        email = parts[0]
        password = parts[1]
        api_key = parts[2]

        conn_id = f"bb_{api_key[:12]}"
        name = f"blackbox-{email.split('@')[0][:12]}"

        # Match9Router's expected data format
        data = json.dumps({
            "apiKey": api_key,
            "testStatus": "active",
            "providerSpecificData": {
                "baseUrl": BASE_URL,
                "connectionProxyEnabled": False,
                "connectionProxyUrl": "",
                "connectionNoProxy": "",
            },
        })

        # Skip if already exists
        cursor.execute("SELECT id FROM providerConnections WHERE id = ?", (conn_id,))
        if cursor.fetchone():
            # Update existing entry with correct format
            cursor.execute(
                """UPDATE providerConnections
                   SET authType = ?, data = ?, updatedAt = datetime('now')
                   WHERE id = ?""",
                (AUTH_TYPE, data, conn_id),
            )
            continue

        cursor.execute(
            """INSERT INTO providerConnections
               (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, 50, 1, ?, datetime('now'), datetime('now'))""",
            (conn_id, PROVIDER, AUTH_TYPE, name, email, data),
        )
        injected += 1

    conn.commit()
    conn.close()
    return injected


def list_injected(db_path: str | None = None) -> list[dict[str, Any]]:
    db = Path(db_path) if db_path else find_9router_db()
    if db is None or not db.exists():
        return []

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM providerConnections WHERE provider = ?", (PROVIDER,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def remove_keys(db_path: str | None = None) -> int:
    db = Path(db_path) if db_path else find_9router_db()
    if db is None:
        return 0

    conn = sqlite3.connect(str(db))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM providerConnections WHERE provider = ?", (PROVIDER,))
    removed = cursor.rowcount
    conn.commit()
    conn.close()
    return removed
