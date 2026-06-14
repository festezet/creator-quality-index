#!/usr/bin/env python3
"""Migrate fetch_progress.json -> download_progress table in benchmark.db.

Idempotent: INSERT OR REPLACE. Source JSON is preserved.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared_lib.db import get_connection, execute_db, query_db

CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESS_PATH = os.path.join(CQI_ROOT, "data", "fetch_progress.json")
DB_PATH = os.path.join(CQI_ROOT, "data", "benchmark.db")

# Map JSON status strings -> DB status enum
STATUS_MAP = {
    "ok": "ok",
    "download_failed": "download_failed",
    "rate_limited": "rate_limited",
    "timeout": "timeout",
    "whisper_failed": "whisper_failed",
}


def main():
    if not os.path.exists(PROGRESS_PATH):
        print(f"No progress file at {PROGRESS_PATH}, nothing to migrate.")
        return 0

    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    fetched = data.get("fetched", {})
    print(f"Source: {len(fetched)} entries in fetch_progress.json")

    conn = get_connection(DB_PATH)
    inserted = 0
    skipped = 0

    for video_id, info in fetched.items():
        ch_id = info.get("channel_id")
        if ch_id is None:
            skipped += 1
            continue
        status = STATUS_MAP.get(info.get("status", ""), None)
        if status is None:
            skipped += 1
            continue
        execute_db(conn, """
            INSERT INTO download_progress
            (video_id, channel_id, status, attempts, chars, words, lang, source,
             completed_at)
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                status = excluded.status,
                chars = excluded.chars,
                words = excluded.words,
                lang = excluded.lang,
                source = excluded.source,
                last_attempt_at = datetime('now'),
                completed_at = excluded.completed_at
        """, (
            video_id, ch_id, status,
            info.get("chars"), info.get("words"),
            info.get("lang"), info.get("source"),
            "datetime('now')" if status == "ok" else None,
        ))
        inserted += 1

    # Stats post-migration
    rows = query_db(conn, """
        SELECT status, COUNT(*) AS n FROM download_progress GROUP BY status
    """)
    conn.close()

    print(f"Migrated: {inserted} (skipped {skipped})")
    print("DB stats by status:")
    for r in rows:
        print(f"  {r['status']}: {r['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
