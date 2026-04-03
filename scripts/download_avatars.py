"""Download channel avatars locally from Google URLs stored in benchmark.db.

Reads thumbnail_url (Google CDN), downloads to frontend/static/avatars/<id>.webp,
updates thumbnail_url to local path /static/avatars/<id>.webp.
Processes in parallel with rate-limiting to avoid Google 429s.
"""
import sqlite3
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "benchmark.db",
)
AVATAR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "static", "avatars",
)
WORKERS = 4  # Conservative to avoid 429


def download_avatar(ch_id, name, remote_url):
    """Download a single avatar image."""
    out_path = os.path.join(AVATAR_DIR, f"{ch_id}.webp")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
        return ch_id, name, out_path, None  # Already downloaded

    try:
        req = urllib.request.Request(remote_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; CQI/1.0)",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) < 100:
                return ch_id, name, None, "response too small"
            with open(out_path, "wb") as f:
                f.write(data)
            return ch_id, name, out_path, None
    except Exception as e:
        return ch_id, name, None, str(e)[:80]


def main():
    os.makedirs(AVATAR_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get channels with remote Google thumbnail URLs
    rows = conn.execute(
        "SELECT id, name, thumbnail_url FROM channels "
        "WHERE thumbnail_url IS NOT NULL AND thumbnail_url LIKE 'https://%'"
    ).fetchall()

    if not rows:
        print("No remote thumbnails to download.")
        conn.close()
        return

    print(f"Downloading {len(rows)} avatars ({WORKERS} workers)...")

    success = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(download_avatar, row["id"], row["name"], row["thumbnail_url"]): row
            for row in rows
        }

        for future in as_completed(futures):
            ch_id, name, local_path, err = future.result()

            if local_path:
                local_url = f"/static/avatars/{ch_id}.webp"
                conn.execute(
                    "UPDATE channels SET thumbnail_url = ? WHERE id = ?",
                    (local_url, ch_id),
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
