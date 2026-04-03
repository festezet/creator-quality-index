"""Fetch YouTube channel avatar URLs using yt-dlp and store in benchmark.db.

Uses yt-dlp --flat-playlist to get channel metadata including avatar_uncropped.
Processes channels in parallel (8 workers) for speed.
Only fetches for channels that don't already have a thumbnail_url.
"""
import sqlite3
import subprocess
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "benchmark.db",
)
WORKERS = 8


def fetch_avatar(name, url):
    """Extract channel avatar URL via yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--playlist-items", "0", "-J", url],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return name, None, result.stderr.strip()[:80]

        data = json.loads(result.stdout)
        # Look for avatar (square profile picture)
        for t in data.get("thumbnails", []):
            if t.get("id") == "avatar_uncropped":
                return name, t["url"], None
        # Fallback: 900x900 avatar
        for t in data.get("thumbnails", []):
            if t.get("id") == "7" and t.get("width") == 900:
                return name, t["url"], None
        return name, None, "no avatar in thumbnails"
    except subprocess.TimeoutExpired:
        return name, None, "timeout"
    except (json.JSONDecodeError, KeyError) as e:
        return name, None, str(e)


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get channels without thumbnail
    rows = conn.execute(
        "SELECT id, name, url FROM channels WHERE thumbnail_url IS NULL"
    ).fetchall()

    if not rows:
        print("All channels already have thumbnails.")
        conn.close()
        return

    print(f"Fetching avatars for {len(rows)} channels ({WORKERS} workers)...")

    success = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(fetch_avatar, row["name"], row["url"]): row["id"]
            for row in rows
        }

        for future in as_completed(futures):
            ch_id = futures[future]
            name, avatar_url, err = future.result()

            if avatar_url:
                # Resize to 176px for small avatars (replace =s0 with =s176)
                small_url = avatar_url.replace("=s0", "=s176")
                conn.execute(
                    "UPDATE channels SET thumbnail_url = ? WHERE id = ?",
                    (small_url, ch_id),
                )
                conn.commit()
                success += 1
                print(f"  OK  {name}")
            else:
                failed += 1
                print(f"  ERR {name}: {err}")

    conn.close()
    print(f"\nDone: {success} OK, {failed} failed (out of {len(rows)})")


if __name__ == "__main__":
    main()
