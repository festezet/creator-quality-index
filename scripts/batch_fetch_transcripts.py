#!/usr/bin/env python3
"""Phase 2 — Fetch transcripts for discovered videos, store in ai-video-studio.

Reads video_manifest.json (Phase 1 output), fetches transcripts via
youtube-transcript-api, stores each in AVS (library.db + media/{vid}/transcript.json).

Features:
- Incremental: skips videos already in AVS with has_transcript=1
- Ban detection + exponential backoff (IpBlocked/RequestBlocked)
- Resume-safe via progress tracking
- Stores in ai-video-studio for cross-project reuse

Usage:
    python3 batch_fetch_transcripts.py [--channel-id ID] [--limit N] [--delay SEC] [--dry-run]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared_lib.db import get_connection, query_db, execute_db
from youtube_transcript_api import YouTubeTranscriptApi, IpBlocked, RequestBlocked

# Paths
CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(CQI_ROOT, "data", "video_manifest.json")
PROGRESS_PATH = os.path.join(CQI_ROOT, "data", "fetch_progress.json")

# AVS paths
AVS_ROOT = "/data/projects/ai-video-studio"
AVS_DB_PATH = os.path.join(AVS_ROOT, "data", "library.db")
AVS_MEDIA_DIR = os.path.join(AVS_ROOT, "data", "media")

# Timing
DELAY_OK = 2        # seconds between successful fetches
DELAY_FAIL = 4      # seconds after non-ban failure
COOLDOWN_MIN = 300   # 5 min initial cooldown on IP ban
COOLDOWN_MAX = 3600  # 1 hour max cooldown
MAX_BAN_RETRIES = 10


def load_manifest():
    """Load video manifest from Phase 1."""
    if not os.path.exists(MANIFEST_PATH):
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        print("Run batch_discover_videos.py first (Phase 1).")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_progress():
    """Load fetch progress (resume-safe)."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"fetched": {}, "stats": {"ok": 0, "no_transcript": 0, "banned_skip": 0}}


def save_progress(progress):
    """Save progress incrementally."""
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def get_avs_existing_videos():
    """Get set of video_ids already in AVS with transcripts."""
    if not os.path.exists(AVS_DB_PATH):
        return set()
    conn = get_connection(AVS_DB_PATH)
    rows = query_db(conn, "SELECT video_id FROM library WHERE has_transcript = 1")
    conn.close()
    return {row["video_id"] for row in rows}


def store_in_avs(video_id, title, transcript_text, language, channel_name):
    """Store transcript in ai-video-studio (library.db + media file)."""
    conn = get_connection(AVS_DB_PATH)

    # Insert or update library entry
    execute_db(conn, """
        INSERT OR REPLACE INTO library
        (video_id, title, source_url, source_type, has_transcript, language,
         word_count, channel_name, updated_at)
        VALUES (?, ?, ?, 'youtube', 1, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        video_id, title,
        f"https://www.youtube.com/watch?v={video_id}",
        language, len(transcript_text.split()), channel_name,
    ))
    conn.close()

    # Write transcript JSON file
    media_dir = os.path.join(AVS_MEDIA_DIR, video_id)
    os.makedirs(media_dir, exist_ok=True)
    transcript_path = os.path.join(media_dir, "transcript.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump({
            "text": transcript_text,
            "language": language,
            "video_id": video_id,
            "title": title,
            "channel_name": channel_name,
        }, f, ensure_ascii=False, indent=2)


def fetch_with_ban_detection(video_id, languages):
    """Fetch transcript, detecting IP bans.

    Returns:
        (transcript_text, is_banned) tuple.
    """
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id, languages=languages)
        return " ".join(snippet.text for snippet in transcript), False
    except (IpBlocked, RequestBlocked):
        return None, True
    except Exception as e:
        err_str = str(e).lower()
        if "blocking" in err_str or "ip" in err_str:
            return None, True
        return None, False


def check_ban_status():
    """Quick test if IP is currently banned."""
    try:
        ytt = YouTubeTranscriptApi()
        ytt.fetch("jNQXAC9IVRw")  # First YouTube video ever
        return False
    except (IpBlocked, RequestBlocked):
        return True
    except Exception as e:
        if "blocking" in str(e).lower() or "ip" in str(e).lower():
            return True
        return False


def wait_for_ban_lift(cooldown):
    """Wait for IP ban to lift with periodic checks."""
    print(f"\n>>> IP BANNED — cooling down {cooldown}s ({cooldown // 60}min)...")
    time.sleep(cooldown * 0.8)
    remaining = cooldown * 0.2
    while remaining > 0:
        time.sleep(min(30, remaining))
        remaining -= 30
        if not check_ban_status():
            print(">>> Ban lifted! Resuming...")
            return True
    if not check_ban_status():
        print(">>> Ban lifted! Resuming...")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Fetch transcripts for CQI videos (Phase 2)")
    parser.add_argument("--channel-id", type=int, help="Process single channel by CQI DB id")
    parser.add_argument("--limit", type=int, default=26, help="Max videos per channel (default: 26)")
    parser.add_argument("--delay", type=float, default=DELAY_OK, help=f"Delay between fetches (default: {DELAY_OK}s)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without fetching")
    args = parser.parse_args()

    manifest = load_manifest()
    progress = load_progress()
    avs_existing = get_avs_existing_videos()

    # Filter manifest if --channel-id
    if args.channel_id:
        manifest = [m for m in manifest if m["channel_id"] == args.channel_id]
        if not manifest:
            print(f"Channel ID {args.channel_id} not found in manifest.")
            sys.exit(1)

    # Build work list: (channel_entry, video_id) pairs
    work = []
    for entry in manifest:
        video_ids = entry.get("video_ids", [])[:args.limit]
        ch_id = entry["channel_id"]
        for vid in video_ids:
            # Skip if already in AVS or already processed
            if vid in avs_existing:
                continue
            if vid in progress["fetched"]:
                continue
            work.append((entry, vid))

    total_in_avs = len(avs_existing)
    total_in_progress = len(progress["fetched"])
    print(f"Manifest: {len(manifest)} channels")
    print(f"Already in AVS: {total_in_avs} transcripts")
    print(f"Already processed (this run): {total_in_progress}")
    print(f"To fetch: {len(work)} videos")

    if args.dry_run:
        for entry, vid in work[:20]:
            print(f"  #{entry['channel_id']} {entry['name'][:35]:35s} → {vid}")
        if len(work) > 20:
            print(f"  ... and {len(work) - 20} more")
        return

    # Check ban before starting
    if work and check_ban_status():
        print("\nIP currently banned. Waiting...")
        cooldown = COOLDOWN_MIN
        for _ in range(MAX_BAN_RETRIES):
            if wait_for_ban_lift(cooldown):
                break
            cooldown = min(cooldown * 2, COOLDOWN_MAX)
        else:
            print("Max retries reached. Run again later.")
            return

    ban_retries = 0
    cooldown = COOLDOWN_MIN
    i = 0

    while i < len(work):
        entry, vid = work[i]
        ch_id = entry["channel_id"]
        lang = entry.get("language", "en")
        languages = [lang, "en"] if lang != "en" else ["en"]

        print(f"[{i + 1}/{len(work)}] #{ch_id} {entry['name'][:30]:30s} {vid} ({lang}) ... ",
              end="", flush=True)

        transcript, is_banned = fetch_with_ban_detection(vid, languages)

        if is_banned:
            print("IP BANNED")
            ban_retries += 1
            if ban_retries > MAX_BAN_RETRIES:
                print(f"\n!!! Max ban retries ({MAX_BAN_RETRIES}) exceeded. Stopping.")
                break
            if wait_for_ban_lift(cooldown):
                cooldown = COOLDOWN_MIN
                continue  # Retry same video
            cooldown = min(cooldown * 2, COOLDOWN_MAX)
            continue

        # Reset ban counters
        ban_retries = 0
        cooldown = COOLDOWN_MIN

        if not transcript:
            print("NO TRANSCRIPT")
            progress["fetched"][vid] = {"channel_id": ch_id, "status": "no_transcript"}
            progress["stats"]["no_transcript"] += 1
            save_progress(progress)
            i += 1
            time.sleep(DELAY_FAIL)
            continue

        # Success — store in AVS
        store_in_avs(vid, f"Video {vid}", transcript, lang, entry["name"])

        print(f"OK ({len(transcript)} chars, {len(transcript.split())} words)")
        progress["fetched"][vid] = {
            "channel_id": ch_id,
            "status": "ok",
            "chars": len(transcript),
        }
        progress["stats"]["ok"] += 1
        save_progress(progress)

        i += 1
        if i < len(work):
            time.sleep(args.delay)

    # Summary
    save_progress(progress)
    stats = progress["stats"]
    print(f"\n{'=' * 60}")
    print(f"Done: {stats['ok']} OK, {stats['no_transcript']} no_transcript")
    print(f"Total in AVS: {len(get_avs_existing_videos())} transcripts")
    print(f"Progress saved to {PROGRESS_PATH}")


if __name__ == "__main__":
    main()
