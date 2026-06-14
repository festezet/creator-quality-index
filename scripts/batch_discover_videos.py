#!/usr/bin/env python3
"""Phase 1 — Discover recent videos for all CQI channels.

Uses yt-dlp --flat-playlist to get up to 30 recent video IDs per channel.
Resume-safe: skips channels already in the manifest.

Usage:
    python3 batch_discover_videos.py [--channel-id ID] [--limit N] [--delay SEC]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from backend.services.transcript_analyzer import get_recent_video_ids
from shared_lib.db import get_connection, query_db

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "video_manifest.json",
)


def load_manifest():
    """Load existing manifest (resume-safe)."""
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_manifest(manifest):
    """Save manifest to disk."""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Discover recent videos for CQI channels")
    parser.add_argument("--channel-id", type=int, help="Process single channel by DB id")
    parser.add_argument("--limit", type=int, default=30, help="Max videos per channel (default: 30)")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between channels (default: 3s)")
    parser.add_argument("--category", help="Filter by category slug")
    args = parser.parse_args()

    conn = get_connection(DB_PATH)
    if args.channel_id:
        channels = query_db(conn, "SELECT id, name, url, language FROM channels WHERE id = ?",
                            [args.channel_id])
    elif args.category:
        channels = query_db(conn, "SELECT id, name, url, language FROM channels WHERE primary_category = ? ORDER BY id",
                            [args.category])
    else:
        channels = query_db(conn, "SELECT id, name, url, language FROM channels ORDER BY id")
    conn.close()

    manifest = load_manifest()
    done_ids = {entry["channel_id"] for entry in manifest}

    to_process = [ch for ch in channels if ch["id"] not in done_ids]
    print(f"Total channels: {len(channels)}")
    print(f"Already in manifest: {len(done_ids)}")
    print(f"To process: {len(to_process)}")

    for i, ch in enumerate(to_process):
        print(f"[{i+1}/{len(to_process)}] #{ch['id']} {ch['name'][:45]:45s} ... ", end="", flush=True)

        video_ids = get_recent_video_ids(ch["url"], count=args.limit)

        entry = {
            "channel_id": ch["id"],
            "name": ch["name"],
            "url": ch["url"],
            "language": ch.get("language", "en"),
            "video_ids": video_ids,
            "total_found": len(video_ids),
        }
        manifest.append(entry)
        save_manifest(manifest)

        if video_ids:
            print(f"{len(video_ids)} videos")
        else:
            print("NO VIDEOS")

        if i < len(to_process) - 1:
            time.sleep(args.delay)

    # Summary
    total_videos = sum(e["total_found"] for e in manifest)
    channels_with_videos = sum(1 for e in manifest if e["total_found"] > 0)
    print(f"\n{'='*60}")
    print(f"Manifest: {len(manifest)} channels, {channels_with_videos} with videos, {total_videos} total video IDs")
    print(f"Saved to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
