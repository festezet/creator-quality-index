#!/usr/bin/env python3
"""Batch fetch transcripts via YouTube transcript API (safe mode).

Conservative rate-limiting with random delays to avoid IP ban.

Usage:
    python3 batch_fetch_transcripts_safe.py              # All remaining
    python3 batch_fetch_transcripts_safe.py --limit 50   # 50 channels
    python3 batch_fetch_transcripts_safe.py --status      # Progress
"""
import json
import os
import random
import sys
import time

from youtube_transcript_api import YouTubeTranscriptApi

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from backend.services.transcript_analyzer import get_recent_video_id, MAX_TRANSCRIPT_CHARS
from shared_lib.db import get_connection, query_db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTPUT = os.path.join(DATA_DIR, "all_transcripts.json")

DELAY_MIN = 5
DELAY_MAX = 10


def load_existing():
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(results):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def fetch_transcript(video_id, languages=None):
    """Fetch transcript via YouTube API. Returns (text, title) or (None, None)."""
    if languages is None:
        languages = ["en"]
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id, languages=languages)
        text = " ".join(t.text for t in transcript)
        return text
    except Exception as e:
        err_name = type(e).__name__
        if "IpBlocked" in err_name or "TooManyRequests" in err_name:
            return "BANNED"
        return None


def main():
    if "--status" in sys.argv:
        results = load_existing()
        ok = sum(1 for r in results if r.get("status") == "ok")
        fails = len(results) - ok
        conn = get_connection(DB_PATH)
        total = query_db(conn, "SELECT COUNT(*) as c FROM channels WHERE is_reviewed = 1")[0]["c"]
        scored = query_db(conn, "SELECT COUNT(*) as c FROM channels WHERE ai_score_research IS NOT NULL")[0]["c"]
        conn.close()
        print(f"Reviewed: {total} | AI scored: {scored} | Transcripts: {ok} OK, {fails} fail")
        return

    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    conn = get_connection(DB_PATH)
    remaining = query_db(conn, """
        SELECT id, name, url, tier, language, primary_category
        FROM channels WHERE is_reviewed = 1 AND ai_score_research IS NULL
        ORDER BY id
    """)
    conn.close()

    results = load_existing()
    done_ids = {r["id"] for r in results}
    to_process = [ch for ch in remaining if ch["id"] not in done_ids]

    if limit:
        to_process = to_process[:limit]

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    print(f"Remaining in DB: {len(remaining)}")
    print(f"Already fetched: {len(done_ids)} ({ok_count} OK)")
    print(f"To process now: {len(to_process)}")
    print()

    ban_count = 0

    for i, ch in enumerate(to_process):
        cid = ch["id"]
        lang = ch["language"] or "en"
        langs = [lang] if lang == "en" else [lang, "en"]

        print(f"[{i+1}/{len(to_process)}] [{ch['tier']}] #{cid} {ch['name'][:40]:40s} ... ",
              end="", flush=True)

        # Get video ID via yt-dlp (not rate-limited by YouTube transcript API)
        video_id = get_recent_video_id(ch["url"])
        if not video_id:
            print("NO_VIDEO")
            results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                           "category": ch["primary_category"], "language": lang,
                           "status": "no_video"})
            save_results(results)
            continue

        # Fetch transcript
        text = fetch_transcript(video_id, langs)

        if text == "BANNED":
            print("BANNED! Arret immediat.")
            print(f"\nBan detecte apres {i} channels. Resultats sauvegardes.")
            save_results(results)
            sys.exit(2)

        if text is None or len(text) < 50:
            print(f"NO_TRANSCRIPT (vid={video_id})")
            results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                           "category": ch["primary_category"], "language": lang,
                           "video_id": video_id, "status": "no_transcript"})
            save_results(results)
        else:
            truncated = text[:MAX_TRANSCRIPT_CHARS]
            ok_count += 1
            print(f"OK ({len(text)} chars)")
            results.append({
                "id": cid, "name": ch["name"], "tier": ch["tier"],
                "category": ch["primary_category"], "language": lang,
                "video_id": video_id, "transcript": truncated,
                "transcript_length": len(text), "status": "ok", "source": "youtube_api",
            })
            save_results(results)

        if ok_count % 20 == 0 and ok_count > 0:
            print(f"  >>> {ok_count} transcripts OK")

        # Random delay 5-10s
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        time.sleep(delay)

    total_ok = sum(1 for r in results if r.get("status") == "ok")
    total_fail = len(results) - total_ok
    print(f"\n{'='*60}")
    print(f"Done: {total_ok} OK, {total_fail} failed")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
