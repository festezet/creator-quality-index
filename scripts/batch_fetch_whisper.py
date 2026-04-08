#!/usr/bin/env python3
"""Batch fetch transcripts via yt-dlp audio download + Whisper transcription.

Bypasses YouTube subtitle API rate-limiting by:
1. Downloading 10 min of audio per channel via yt-dlp
2. Transcribing locally via Whisper (localhost:9001)

Features:
- Incremental save (resume-safe)
- Progress tracking
- Configurable audio duration and language

Usage:
    python3 batch_fetch_whisper.py                    # Process all remaining
    python3 batch_fetch_whisper.py --limit 50         # Process 50 channels
    python3 batch_fetch_whisper.py --status            # Show progress
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from backend.services.transcript_analyzer import get_recent_video_id, MAX_TRANSCRIPT_CHARS
from shared_lib.db import get_connection, query_db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTPUT = os.path.join(DATA_DIR, "all_transcripts.json")

WHISPER_URL = "http://localhost:9001/v1/audio/transcriptions"
AUDIO_DURATION_SEC = 600  # 10 minutes
DELAY_BETWEEN = 2  # seconds between channels


def load_existing():
    """Load previously fetched results."""
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(results):
    """Save results incrementally."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def download_audio(video_id, output_dir, duration_sec=AUDIO_DURATION_SEC):
    """Download audio from YouTube video via yt-dlp.

    Args:
        video_id: YouTube video ID.
        output_dir: Directory to save the mp3 file.
        duration_sec: Max seconds to download.

    Returns:
        Path to downloaded mp3 file, or None on failure.
    """
    output_template = os.path.join(output_dir, "audio.%(ext)s")
    expected_mp3 = os.path.join(output_dir, "audio.mp3")
    try:
        result = subprocess.run(
            [
                "yt-dlp", "-x", "--audio-format", "mp3",
                "--audio-quality", "5",
                "--download-sections", f"*0-{duration_sec}",
                "-o", output_template,
                "--no-playlist",
                "--no-warnings",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0 and os.path.exists(expected_mp3):
            return expected_mp3
        # yt-dlp may output error info
        if result.stderr:
            print(f"yt-dlp stderr: {result.stderr[:100]}", end="")
    except subprocess.TimeoutExpired:
        print("TIMEOUT", end="")
    except FileNotFoundError:
        print("yt-dlp not found", end="")
    return None


def get_video_title(video_id):
    """Get video title via yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--print", "%(title)s", "--no-download",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "Unknown"


def whisper_transcribe(audio_path, language="en"):
    """Transcribe audio file via local Whisper service.

    Returns transcript text, or None on failure.
    """
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                WHISPER_URL,
                files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
                data={"model": "Systran/faster-whisper-base", "language": language, "response_format": "json"},
                timeout=600,
            )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("text", "")
    except Exception as e:
        print(f"Whisper error: {e}")
    return None


def show_status():
    """Show overall progress."""
    conn = get_connection(DB_PATH)
    total = query_db(conn, "SELECT COUNT(*) as c FROM channels WHERE is_reviewed = 1")[0]["c"]
    scored = query_db(conn, "SELECT COUNT(*) as c FROM channels WHERE ai_score_research IS NOT NULL")[0]["c"]
    conn.close()

    results = load_existing()
    ok = sum(1 for r in results if r.get("status") == "ok")
    failed = sum(1 for r in results if r.get("status") != "ok")

    print(f"Channels reviewed: {total}")
    print(f"AI scored in DB: {scored}")
    print(f"Transcripts fetched: {ok} OK, {failed} failed")
    print(f"Remaining: {total - scored - ok}")


def main():
    if "--status" in sys.argv:
        show_status()
        return

    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    # Check Whisper service
    try:
        resp = requests.get("http://localhost:9001/v1/models", timeout=5)
        if resp.status_code != 200:
            print("ERROR: Whisper service not responding. Check Docker.")
            sys.exit(1)
    except Exception:
        print("ERROR: Cannot reach Whisper at localhost:9001")
        sys.exit(1)

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
    print(f"Total remaining in DB: {len(remaining)}")
    print(f"Already fetched: {len(done_ids)} ({ok_count} OK)")
    print(f"To process now: {len(to_process)}")
    print()

    for i, ch in enumerate(to_process):
        cid = ch["id"]
        lang = ch["language"] or "en"

        print(f"[{i+1}/{len(to_process)}] [{ch['tier']}] #{cid} {ch['name'][:40]:40s} ({lang}) ... ",
              end="", flush=True)

        # Step 1: Get video ID
        video_id = get_recent_video_id(ch["url"])
        if not video_id:
            print("NO VIDEO")
            results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                           "category": ch["primary_category"], "language": lang,
                           "status": "no_video"})
            save_results(results)
            continue

        # Step 2: Download audio to temp directory
        tmp_dir = tempfile.mkdtemp(prefix="cqi_audio_")

        try:
            print(f"dl..", end="", flush=True)
            audio_path = download_audio(video_id, tmp_dir)
            if not audio_path:
                print(f" DL_FAIL (vid={video_id})")
                results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                               "category": ch["primary_category"], "language": lang,
                               "video_id": video_id, "status": "dl_fail"})
                save_results(results)
                continue

            # Step 3: Transcribe with Whisper
            print(f"whisper..", end="", flush=True)
            whisper_lang = lang if len(lang) == 2 else lang[:2]
            transcript = whisper_transcribe(audio_path, whisper_lang)

            if not transcript or len(transcript) < 50:
                print(f" WHISPER_FAIL (vid={video_id})")
                results.append({"id": cid, "name": ch["name"], "tier": ch["tier"],
                               "category": ch["primary_category"], "language": lang,
                               "video_id": video_id, "status": "whisper_fail"})
                save_results(results)
                continue

            # Step 4: Get title and save
            title = get_video_title(video_id)
            truncated = transcript[:MAX_TRANSCRIPT_CHARS]
            ok_count += 1

            print(f" OK ({len(transcript)} chars, vid={video_id})")
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
                "source": "whisper",
            })
            save_results(results)

            if ok_count % 10 == 0:
                print(f"  >>> {ok_count} transcripts fetched so far")

        finally:
            # Clean up temp directory
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

        time.sleep(DELAY_BETWEEN)

    # Final summary
    save_results(results)
    total_ok = sum(1 for r in results if r.get("status") == "ok")
    total_fail = len(results) - total_ok
    print(f"\n{'='*60}")
    print(f"Done: {total_ok} OK, {total_fail} failed")
    print(f"Total processed: {len(results)}/{len(remaining)}")
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
