#!/usr/bin/env python3
"""Substitute failed (members-only) videos by discovering more from the same channels.

Two-step process:
  1. Re-discover up to --limit video IDs per channel (enriches manifest)
  2. Inject substitutes as 'pending' into download_progress for channels < 26 ok/downloaded

Does NOT delete failed entries — adds new pending ones alongside them.
Phase A then picks up the new pending videos naturally.

Usage:
    python3 scripts/substitute_failed.py --dry-run
    python3 scripts/substitute_failed.py
    python3 scripts/substitute_failed.py --limit 80 --delay 3
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
TARGET_PER_CHANNEL = 26


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_manifest(manifest):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_channels_needing_substitutes(conn):
    """Channels with download_failed AND fewer than TARGET ok/downloaded."""
    return query_db(conn, """
        SELECT
            dp.channel_id,
            c.name,
            c.url,
            SUM(CASE WHEN dp.status = 'download_failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN dp.status IN ('ok', 'downloaded') THEN 1 ELSE 0 END) as good,
            SUM(CASE WHEN dp.status = 'pending' THEN 1 ELSE 0 END) as pending_count
        FROM download_progress dp
        JOIN channels c ON c.id = dp.channel_id
        WHERE dp.channel_id IN (
            SELECT DISTINCT channel_id FROM download_progress
            WHERE status = 'download_failed'
        )
        GROUP BY dp.channel_id
        HAVING good + pending_count < ?
        ORDER BY good ASC
    """, [TARGET_PER_CHANNEL])


def get_all_known_video_ids(conn, channel_id):
    """All video IDs already in DB for this channel (any status)."""
    rows = query_db(conn, """
        SELECT video_id FROM download_progress WHERE channel_id = ?
    """, [channel_id])
    return {row["video_id"] for row in rows}


def main():
    parser = argparse.ArgumentParser(
        description="Substitute failed videos with new discoveries (2-step: enrich manifest + inject pending)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without modifying anything")
    parser.add_argument("--limit", type=int, default=80,
                        help="Discover up to N videos per channel (default: 80)")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Delay between yt-dlp discovery calls (default: 3s)")
    parser.add_argument("--limit-channels", type=int, default=0,
                        help="Process only N channels (0=all)")
    args = parser.parse_args()

    conn = get_connection(DB_PATH)
    channels = get_channels_needing_substitutes(conn)
    print(f"Channels needing substitutes (< {TARGET_PER_CHANNEL} good): {len(channels)}")

    if not channels:
        print("Nothing to do.")
        conn.close()
        return

    if args.limit_channels > 0:
        channels = channels[:args.limit_channels]
        print(f"Processing first {args.limit_channels} channels")

    manifest = load_manifest()
    manifest_by_id = {e["channel_id"]: e for e in manifest}

    total_discovered = 0
    total_injected = 0
    channels_enriched = 0

    for i, ch in enumerate(channels):
        ch_id = ch["channel_id"]
        ch_name = ch["name"]
        ch_url = ch["url"]
        n_good = ch["good"]
        n_failed = ch["failed"]
        n_pending = ch["pending_count"]
        needed = TARGET_PER_CHANNEL - (n_good + n_pending)

        print(f"\n[{i+1}/{len(channels)}] #{ch_id} {ch_name[:40]:40s} "
              f"(good={n_good}, pending={n_pending}, failed={n_failed}, need={needed})")

        if needed <= 0:
            print(f"  -> Already has enough (good+pending >= {TARGET_PER_CHANNEL})")
            continue

        # Step 1: Re-discover video IDs
        discovered = get_recent_video_ids(ch_url, count=args.limit)
        if not discovered:
            print(f"  -> Discovery failed (channel unavailable?)")
            if i < len(channels) - 1:
                time.sleep(args.delay)
            continue

        total_discovered += len(discovered)

        # Update manifest with broader discovery
        if ch_id in manifest_by_id:
            entry = manifest_by_id[ch_id]
            old_count = len(entry.get("video_ids", []))
            # Merge: keep order from discovery, append any old IDs not in discovery
            old_set = set(entry.get("video_ids", []))
            merged = list(discovered)
            for vid in entry.get("video_ids", []):
                if vid not in set(discovered):
                    merged.append(vid)
            entry["video_ids"] = merged
            entry["total_found"] = len(merged)
            print(f"  -> Discovered {len(discovered)} videos "
                  f"(manifest: {old_count} -> {len(merged)})")
        else:
            print(f"  -> Channel not in manifest, adding")
            entry = {
                "channel_id": ch_id,
                "name": ch_name,
                "url": ch_url,
                "video_ids": list(discovered),
                "total_found": len(discovered),
            }
            manifest.append(entry)
            manifest_by_id[ch_id] = entry

        channels_enriched += 1

        # Step 2: Find new candidates not already in DB
        known = get_all_known_video_ids(conn, ch_id)
        new_candidates = [vid for vid in discovered if vid not in known]
        to_inject = new_candidates[:needed]

        print(f"  -> New candidates: {len(new_candidates)}, injecting: {len(to_inject)}/{needed}")

        if not to_inject:
            print(f"  -> No new videos available (all discovered already in DB)")
            if i < len(channels) - 1:
                time.sleep(args.delay)
            continue

        if args.dry_run:
            for vid in to_inject[:5]:
                print(f"     [DRY] Would add {vid} as pending")
            if len(to_inject) > 5:
                print(f"     [DRY] ... and {len(to_inject) - 5} more")
            total_injected += len(to_inject)
        else:
            for vid in to_inject:
                execute_db(conn, """
                    INSERT OR IGNORE INTO download_progress
                    (video_id, channel_id, status, attempts)
                    VALUES (?, ?, 'pending', 0)
                """, [vid, ch_id])
            total_injected += len(to_inject)

        if i < len(channels) - 1:
            time.sleep(args.delay)

    # Save manifest (even in dry-run we skip)
    if not args.dry_run and channels_enriched > 0:
        save_manifest(manifest)

    print(f"\n{'='*60}")
    print(f"Channels processed: {len(channels)}")
    print(f"Channels enriched (manifest updated): {channels_enriched}")
    print(f"Total videos discovered: {total_discovered}")
    print(f"Total new pending injected: {total_injected}")
    if args.dry_run:
        print("(DRY RUN — no changes made)")
    else:
        print(f"Manifest saved. Run Phase A to download the new pending videos.")

    conn.close()


if __name__ == "__main__":
    main()
