#!/usr/bin/env python3
"""Batch fetch transcripts for ALL remaining channels.

Features:
- Incremental save (resume-safe)
- Exponential backoff on rate-limiting
- Auto-retry after cooldown period
- Progress tracking with stats
- Distinguishes IP ban vs genuine no-transcript
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from backend.services.transcript_analyzer import (
    get_recent_video_id, get_video_title, MAX_TRANSCRIPT_CHARS,
)
from shared_lib.db import get_connection, query_db
from youtube_transcript_api import YouTubeTranscriptApi, IpBlocked, RequestBlocked

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "all_transcripts.json")
DELAY_OK = 3        # seconds between successful requests
DELAY_FAIL = 5      # seconds after non-ban failure
COOLDOWN_MIN = 300   # 5 min initial cooldown on IP ban
COOLDOWN_MAX = 3600  # 1 hour max cooldown
MAX_RETRIES = 10     # max ban-cooldown retries before giving up


def load_existing():
    """Load previously fetched results."""
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(results):
    """Save results incrementally."""
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def fetch_transcript_with_ban_detection(video_id, languages):
    """Fetch transcript, distinguishing IP ban from genuine unavailability.

    Returns:
        (transcript_text, is_banned) tuple.
        transcript_text is None if unavailable.
        is_banned is True if the failure was due to IP blocking.
    """
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id, languages=languages)
        return " ".join(snippet.text for snippet in transcript), False
    except (IpBlocked, RequestBlocked):
        return None, True
    except Exception as e:
        err_str = str(e)
        if "blocking" in err_str.lower() or "IP" in err_str:
            return None, True
        return None, False


def check_ban_status():
    """Quick test if IP is still banned."""
    try:
        ytt = YouTubeTranscriptApi()
        ytt.fetch("jNQXAC9IVRw")  # First YouTube video ever - always has subs
        return False  # Not banned
    except (IpBlocked, RequestBlocked):
        return True
    except Exception as e:
        if "blocking" in str(e).lower() or "IP" in str(e):
            return True
        return False  # Different error, not a ban


def wait_for_ban_lift(cooldown):
    """Wait for IP ban to lift with periodic checks."""
    print(f"\n>>> IP BANNED — cooling down {cooldown}s ({cooldown//60}min)...")
    # Wait most of the cooldown
    time.sleep(cooldown * 0.8)
    # Then check every 30s
    remaining = cooldown * 0.2
    while remaining > 0:
        time.sleep(min(30, remaining))
        remaining -= 30
        if not check_ban_status():
            print(">>> Ban lifted! Resuming...")
            return True
    # Final check
    if not check_ban_status():
        print(">>> Ban lifted! Resuming...")
        return True
    return False


def main():
    conn = get_connection(DB_PATH)
    remaining = query_db(conn, """
        SELECT id, name, url, tier, language, primary_category
        FROM channels WHERE is_reviewed = 1 AND ai_score_research IS NULL
        ORDER BY id
    """)
    conn.close()

    results = load_existing()
    done_ids = {r["id"] for r in results}
    # Skip already-fetched (including failed ones we know about)
    to_process = [ch for ch in remaining if ch["id"] not in done_ids]

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    print(f"Total remaining in DB: {len(remaining)}")
    print(f"Already processed: {len(done_ids)} ({ok_count} OK)")
    print(f"To process now: {len(to_process)}")

    # Check if currently banned before starting
    if check_ban_status():
        print("\nIP currently banned. Waiting for lift...")
        cooldown = COOLDOWN_MIN
        for attempt in range(MAX_RETRIES):
            if wait_for_ban_lift(cooldown):
                break
            cooldown = min(cooldown * 2, COOLDOWN_MAX)
            print(f"Still banned. Increasing cooldown to {cooldown}s...")
        else:
            print("Max retries reached. Run again later.")
            return

    ban_retry_count = 0
    cooldown = COOLDOWN_MIN
    i = 0

    while i < len(to_process):
        ch = to_process[i]
        cid = ch["id"]
        lang = ch["language"] or "en"
        languages = [lang, "en"] if lang != "en" else ["en"]

        print(f"[{i+1}/{len(to_process)}] [{ch['tier']}] #{cid} {ch['name'][:40]:40s} ({lang}) ... ",
              end="", flush=True)

        # Get video ID
        video_id = get_recent_video_id(ch["url"])
        if not video_id:
            print("NO VIDEO")
            results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                           "category": ch["primary_category"], "language": lang,
                           "status": "no_video"})
            save_results(results)
            i += 1
            time.sleep(DELAY_FAIL)
            continue

        # Fetch transcript with ban detection
        transcript, is_banned = fetch_transcript_with_ban_detection(video_id, languages)

        if is_banned:
            print(f"IP BANNED (vid={video_id})")
            ban_retry_count += 1
            if ban_retry_count > MAX_RETRIES:
                print(f"\n!!! Max ban retries ({MAX_RETRIES}) exceeded. Stopping.")
                break
            if wait_for_ban_lift(cooldown):
                cooldown = COOLDOWN_MIN  # Reset cooldown on success
                continue  # Retry same channel
            cooldown = min(cooldown * 2, COOLDOWN_MAX)
            continue  # Retry same channel after longer wait

        # Reset ban counters on non-ban response
        ban_retry_count = 0
        cooldown = COOLDOWN_MIN

        if not transcript:
            print(f"NO TRANSCRIPT (vid={video_id})")
            results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                           "category": ch["primary_category"], "language": lang,
                           "video_id": video_id, "status": "no_transcript"})
            save_results(results)
            i += 1
            time.sleep(DELAY_FAIL)
            continue

        title = get_video_title(video_id)
        truncated = transcript[:MAX_TRANSCRIPT_CHARS]
        ok_count += 1

        print(f"OK ({len(transcript)} chars, vid={video_id})")
        results.append({
            "id": cid,
            "name": ch["name"],
            "tier": ch["tier"],
            "category": ch["primary_category"],
            "language": lang,
            "video_id": video_id,
            "video_title": title,
            "transcript": truncated,
            "transcript_length": len(transcript),
            "status": "ok",
        })

        # Save after every OK result
        save_results(results)
        if ok_count % 10 == 0:
            print(f"  >>> {ok_count} transcripts fetched so far")

        i += 1
        time.sleep(DELAY_OK)

    # Final summary
    save_results(results)
    total_ok = sum(1 for r in results if r.get("status") == "ok")
    total_no_video = sum(1 for r in results if r.get("status") == "no_video")
    total_no_transcript = sum(1 for r in results if r.get("status") == "no_transcript")
    print(f"\n{'='*60}")
    print(f"Done: {total_ok} OK, {total_no_video} no_video, {total_no_transcript} no_transcript")
    print(f"Total processed: {len(results)}/{len(remaining)}")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
