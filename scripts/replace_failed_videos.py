#!/usr/bin/env python3
"""Replace failed video downloads with new recent videos from the same channels.

For each channel that has download_failed entries, discovers fresh video IDs
via yt-dlp --flat-playlist, excludes all known video_ids (any status), and
inserts replacements into download_progress as 'pending' + updates manifest.

Usage:
    python3 replace_failed_videos.py [--dry-run] [--limit-channels N] [--discover N]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.transcript_analyzer import get_recent_video_ids
from shared_lib.db import get_connection, query_db, execute_db

CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(CQI_ROOT, "data", "benchmark.db")
MANIFEST_PATH = os.path.join(CQI_ROOT, "data", "video_manifest.json")


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_manifest(manifest):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_channels_with_failures(conn):
    """Get channels that have failed downloads, with count of failures and successes."""
    return query_db(conn, """
        SELECT
            dp.channel_id,
            c.name,
            c.url,
            SUM(CASE WHEN dp.status = 'download_failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN dp.status IN ('ok', 'downloaded') THEN 1 ELSE 0 END) as success
        FROM download_progress dp
        JOIN channels c ON c.id = dp.channel_id
        WHERE dp.channel_id IN (
            SELECT DISTINCT channel_id FROM download_progress WHERE status = 'download_failed'
        )
        GROUP BY dp.channel_id
        ORDER BY failed DESC
    """)


def get_all_known_video_ids(conn, channel_id):
    """All video IDs already in DB for this channel (any status)."""
    rows = query_db(conn, """
        SELECT video_id FROM download_progress WHERE channel_id = ?
    """, [channel_id])
    return {row["video_id"] for row in rows}


def main():
    parser = argparse.ArgumentParser(description="Replace failed videos with new discoveries")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying DB")
    parser.add_argument("--limit-channels", type=int, default=0, help="Process only N channels (0=all)")
    parser.add_argument("--discover", type=int, default=50, help="Discover N recent videos per channel (default: 50)")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between yt-dlp calls (default: 3s)")
    args = parser.parse_args()

    conn = get_connection(DB_PATH)
    channels = get_channels_with_failures(conn)
    print(f"Channels with failures: {len(channels)}")

    if args.limit_channels > 0:
        channels = channels[:args.limit_channels]
        print(f"Processing first {args.limit_channels} channels")

    manifest = load_manifest()
    manifest_by_channel = {e["channel_id"]: e for e in manifest}

    total_replaced = 0
    total_failed_removed = 0

    for i, ch in enumerate(channels):
        ch_id = ch["channel_id"]
        ch_name = ch["name"]
        ch_url = ch["url"]
        n_failed = ch["failed"]
        n_success = ch["success"]

        print(f"\n[{i+1}/{len(channels)}] #{ch_id} {ch_name[:40]:40s} "
              f"(ok={n_success}, failed={n_failed})")

        # Discover recent videos
        discovered = get_recent_video_ids(ch_url, count=args.discover)
        if not discovered:
            print(f"  -> No videos discovered (channel may be empty/unavailable)")
            continue

        # Exclude all known video IDs
        known = get_all_known_video_ids(conn, ch_id)
        new_ids = [vid for vid in discovered if vid not in known]

        # We want to replace up to n_failed videos
        replacements = new_ids[:n_failed]

        print(f"  -> Discovered {len(discovered)}, "
              f"already known {len(discovered) - len(new_ids)}, "
              f"new candidates {len(new_ids)}, "
              f"replacing {len(replacements)}/{n_failed} failed")

        if not replacements:
            print(f"  -> No new videos available for this channel")
            continue

        if args.dry_run:
            for vid in replacements[:5]:
                print(f"     [DRY] Would add {vid}")
            if len(replacements) > 5:
                print(f"     [DRY] ... and {len(replacements) - 5} more")
            total_replaced += len(replacements)
            continue

        # Delete the failed entries (they'll be replaced)
        # Delete oldest failed first, up to len(replacements)
        execute_db(conn, """
            DELETE FROM download_progress
            WHERE video_id IN (
                SELECT video_id FROM download_progress
                WHERE channel_id = ? AND status = 'download_failed'
                LIMIT ?
            )
        """, [ch_id, len(replacements)])
        total_failed_removed += len(replacements)

        # Insert new video IDs as 'pending' (Phase A will pick them up)
        for vid in replacements:
            execute_db(conn, """
                INSERT OR IGNORE INTO download_progress
                (video_id, channel_id, status, attempts)
                VALUES (?, ?, 'pending', 0)
            """, [vid, ch_id])

        # Update manifest
        if ch_id in manifest_by_channel:
            entry = manifest_by_channel[ch_id]
            existing_ids = set(entry.get("video_ids", []))
            for vid in replacements:
                if vid not in existing_ids:
                    entry["video_ids"].append(vid)
            entry["total_found"] = len(entry["video_ids"])
        else:
            new_entry = {
                "channel_id": ch_id,
                "name": ch_name,
                "url": ch_url,
                "video_ids": replacements,
                "total_found": len(replacements),
            }
            manifest.append(new_entry)
            manifest_by_channel[ch_id] = new_entry

        total_replaced += len(replacements)

        if i < len(channels) - 1:
            time.sleep(args.delay)

    if not args.dry_run:
        save_manifest(manifest)

    print(f"\n{'='*60}")
    print(f"Total failed removed: {total_failed_removed}")
    print(f"Total new videos added: {total_replaced}")
    if args.dry_run:
        print("(DRY RUN — no changes made)")
    else:
        print(f"Manifest saved. Run Phase A to download the new videos.")

    conn.close()


if __name__ == "__main__":
    main()
