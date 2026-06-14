#!/usr/bin/env python3
"""Phase 2b — Fetch transcripts via audio download + faster-whisper.

Alternative to batch_fetch_transcripts.py when youtube-transcript-api is IP-banned.
Downloads audio via yt-dlp (not banned), transcribes locally with faster-whisper.

Features:
- Incremental: skips videos already in AVS with has_transcript=1
- Resume-safe via progress tracking (shared with Phase 2)
- Dual storage: AVS library.db (for CQI scoring) + transcriptions.db (PRJ-026 shared)
- Low CPU priority (nice -n 19 recommended)
- Audio files deleted after transcription

Reuses:
- SharedMediaDB from youtube-transcription (PRJ-026) for canonical transcript storage
- AVS library.db + media/{video_id}/transcript.json for CQI pipeline

Usage:
    nice -n 19 python3 batch_whisper_transcripts.py [--channel-id ID] [--limit N] [--delay SEC]
    nice -n 19 python3 batch_whisper_transcripts.py --model base  # Better quality, slower
    nice -n 19 python3 batch_whisper_transcripts.py --stats       # Show progress stats
"""
import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/data/projects/youtube-transcription")

from shared_lib.db import get_connection, query_db, execute_db
from shared_media_db import SharedMediaDB

# Paths
CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(CQI_ROOT, "data", "video_manifest.json")
CQI_DB_PATH = os.path.join(CQI_ROOT, "data", "benchmark.db")

# AVS paths
AVS_ROOT = "/data/projects/ai-video-studio"
AVS_DB_PATH = os.path.join(AVS_ROOT, "data", "library.db")
AVS_MEDIA_DIR = os.path.join(AVS_ROOT, "data", "media")

# Defaults
DEFAULT_MODEL = "tiny"
DEFAULT_MIN_DELAY = 5   # seconds (lower bound of random delay)
DEFAULT_MAX_DELAY = 15  # seconds (upper bound of random delay)
DEFAULT_RATE_LIMIT_PAUSE = 600  # 10 min after 429 detection
RATE_LIMIT_SENTINEL = "RATE_LIMIT"
TIMEOUT_SENTINEL = "TIMEOUT"


def load_manifest():
    """Load video manifest from Phase 1."""
    if not os.path.exists(MANIFEST_PATH):
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        print("Run batch_discover_videos.py first (Phase 1).")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_processed_video_ids(conn, only_final=True):
    """Return set of video_ids already attempted.

    If only_final=True, includes only those we don't want to retry
    (ok + non-retryable failures). Rate-limited and timeout entries
    are excluded so they get retried.
    """
    if only_final:
        rows = query_db(conn, """
            SELECT video_id FROM download_progress
            WHERE status IN ('ok', 'whisper_failed')
        """)
    else:
        rows = query_db(conn, "SELECT video_id FROM download_progress")
    return {row["video_id"] for row in rows}


def get_progress_stats(conn):
    """Return dict {status: count} for download_progress."""
    rows = query_db(conn, """
        SELECT status, COUNT(*) AS n FROM download_progress GROUP BY status
    """)
    return {row["status"]: row["n"] for row in rows}


def record_progress(conn, video_id, channel_id, status, *,
                    chars=None, words=None, lang=None, source=None,
                    error_msg=None):
    """Upsert progress row. Increments attempts on conflict."""
    completed_at = "datetime('now')" if status == "ok" else None
    execute_db(conn, """
        INSERT INTO download_progress
        (video_id, channel_id, status, attempts, chars, words, lang, source,
         error_msg, completed_at)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, CASE WHEN ? = 'ok' THEN datetime('now') END)
        ON CONFLICT(video_id) DO UPDATE SET
            status = excluded.status,
            attempts = download_progress.attempts + 1,
            chars = COALESCE(excluded.chars, download_progress.chars),
            words = COALESCE(excluded.words, download_progress.words),
            lang = COALESCE(excluded.lang, download_progress.lang),
            source = COALESCE(excluded.source, download_progress.source),
            error_msg = excluded.error_msg,
            last_attempt_at = datetime('now'),
            completed_at = CASE WHEN excluded.status = 'ok'
                                THEN datetime('now')
                                ELSE download_progress.completed_at END
    """, (video_id, channel_id, status, chars, words, lang, source,
          error_msg, status))


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
            "source": "whisper",
        }, f, ensure_ascii=False, indent=2)


def store_in_shared_db(shared_db, video_id, title, transcript_text,
                       language, channel_name, whisper_model):
    """Store transcript in shared transcriptions.db (PRJ-026 ecosystem)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    vid_id = shared_db.add_or_update_video(
        url=url, title=title, channel=channel_name, language=language)
    shared_db.add_transcription(
        video_id=vid_id, format="json",
        content=json.dumps({"text": transcript_text}),
        whisper_model=whisper_model)
    shared_db.add_transcription(
        video_id=vid_id, format="plain",
        content=transcript_text,
        whisper_model=whisper_model)


def download_audio(video_id, output_dir, max_secs=600, cookies_path=None):
    """Download first `max_secs` of audio via yt-dlp `--download-sections`.

    Returns:
        - path (str) on success
        - RATE_LIMIT_SENTINEL on 429 / "Too Many Requests" / "Sign in to confirm"
        - TIMEOUT_SENTINEL on subprocess timeout
        - None on any other failure (logs stderr)
    """
    # OPTIM 2026-05-04 : `--download-sections` declenchait un download streame
    # en realtime ~2x (throttling YouTube confirme par speed=2.09x constant).
    # 5 min pour 10min audio. Solution : telecharger l'audio entier (full speed
    # ~13MB/s, 13s pour 180MB), puis trim ffmpeg local en stream copy (~1s).
    # Gain mesure : ~5 min -> ~15s = 20x. Pas de --download-sections ni
    # --force-keyframes-at-cuts. `-x --audio-format mp3` produit un mp3 final
    # par re-encode mais c'est rapide une fois le fichier local.
    output_template = os.path.join(output_dir, f"{video_id}_full.%(ext)s")
    cmd = [
        "yt-dlp", "--js-runtimes", "node",
        "-x", "--audio-format", "mp3", "--audio-quality", "9",
        "--no-warnings",
        "-o", output_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    if cookies_path and os.path.exists(cookies_path):
        cmd[1:1] = ["--cookies", cookies_path]

    # Timeout : download full speed + re-encode mp3 local. 300s couvre les
    # videos jusqu'a ~3h (le bottleneck devient la BP, pas le re-encode).
    dl_timeout = 300

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=dl_timeout,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").lower()
            # Detect rate-limit / bot-challenge signals (vrais blocages serveur)
            # Important : ne PAS confondre avec "sign in to confirm your age"
            # (age-restricted = video specifique a skip, pas un rate-limit).
            rate_signals = (
                "http error 429", "too many requests",
                "confirm you're not a bot", "sign in to confirm you're not a bot",
            )
            if any(sig in stderr for sig in rate_signals):
                snippet = (result.stderr or "")[:200].replace("\n", " ")
                print(f"[RATE_LIMIT] {snippet}")
                return RATE_LIMIT_SENTINEL
            # Generic failure — log first line of stderr
            first_line = (result.stderr or "").split("\n", 1)[0][:200]
            if first_line:
                print(f"[DL_FAIL_ERR] {first_line}")
            return None

        full_path = os.path.join(output_dir, f"{video_id}_full.mp3")
        if not os.path.exists(full_path):
            return None

        # Trim local via ffmpeg stream copy (~1s, no re-encode)
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")
        try:
            trim_result = subprocess.run(
                ["ffmpeg", "-y", "-i", full_path, "-t", str(max_secs),
                 "-c", "copy", "-loglevel", "error", mp3_path],
                capture_output=True, text=True, timeout=60,
            )
            try:
                os.remove(full_path)
            except OSError:
                pass
            if trim_result.returncode != 0 or not os.path.exists(mp3_path):
                # Fallback : utiliser le full file si le trim echoue
                if os.path.exists(full_path):
                    os.replace(full_path, mp3_path)
                else:
                    return None
            return mp3_path
        except subprocess.TimeoutExpired:
            try:
                os.remove(full_path)
            except OSError:
                pass
            return None
    except subprocess.TimeoutExpired:
        return TIMEOUT_SENTINEL
    except OSError as e:
        print(f"[DL_FAIL_OS] {e}")
        return None


def get_video_title(video_id):
    """Get video title via yt-dlp (quick metadata fetch)."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--js-runtimes", "node",
             "--print", "%(title)s", "--skip-download", "--no-warnings", "-q",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return f"Video {video_id}"


def transcribe_audio(audio_path, model, language=None):
    """Transcribe audio file with faster-whisper.

    Returns:
        (transcript_text, detected_language) or (None, None) on failure.
    """
    try:
        kwargs = {}
        if language and language != "auto":
            kwargs["language"] = language

        segments, info = model.transcribe(audio_path, **kwargs)
        text_parts = [seg.text for seg in segments]
        full_text = " ".join(text_parts).strip()

        if not full_text:
            return None, None
        return full_text, info.language
    except Exception as e:
        print(f"WHISPER ERROR: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch transcripts via audio + Whisper (Phase 2b)")
    parser.add_argument("--channel-id", type=int,
                        help="Process single channel by CQI DB id")
    parser.add_argument("--limit", type=int, default=26,
                        help="Max videos per channel (default: 26)")
    parser.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY,
                        help=f"Min random delay between videos (default: {DEFAULT_MIN_DELAY}s)")
    parser.add_argument("--max-delay", type=float, default=DEFAULT_MAX_DELAY,
                        help=f"Max random delay between videos (default: {DEFAULT_MAX_DELAY}s)")
    parser.add_argument("--rate-limit-pause", type=float,
                        default=DEFAULT_RATE_LIMIT_PAUSE,
                        help=f"Pause after RATE_LIMIT (default: {DEFAULT_RATE_LIMIT_PAUSE}s)")
    parser.add_argument("--cookies", default=None,
                        help="Path to cookies.txt (Netscape format) to bypass bot challenges")
    parser.add_argument("--abort-after-rate-limits", type=int, default=3,
                        help="Abort batch after N consecutive rate-limit hits (default: 3)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        choices=["tiny", "base", "small"],
                        help=f"Whisper model size (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched without fetching")
    parser.add_argument("--max-secs", type=int, default=600,
                        help="Max audio duration in seconds (default: 600=10min)")
    parser.add_argument("--stats", action="store_true",
                        help="Show progress stats only")
    args = parser.parse_args()

    manifest = load_manifest()
    db_conn = get_connection(CQI_DB_PATH)
    processed_ids = get_processed_video_ids(db_conn, only_final=True)
    avs_existing = get_avs_existing_videos()

    if args.stats:
        stats = get_progress_stats(db_conn)
        total_videos = sum(
            len(m.get("video_ids", [])[:26]) for m in manifest)
        done = len(avs_existing) + stats.get("ok", 0)
        print(f"Manifest: {len(manifest)} channels, {total_videos} videos (max 26/ch)")
        print(f"In AVS: {len(avs_existing)} transcripts")
        print(f"DB stats: {stats}")
        print(f"Remaining: ~{total_videos - done}")
        db_conn.close()
        return

    # Filter manifest if --channel-id
    if args.channel_id:
        manifest = [m for m in manifest if m["channel_id"] == args.channel_id]
        if not manifest:
            print(f"Channel ID {args.channel_id} not found in manifest.")
            sys.exit(1)

    # Build work list (skip OK + non-retryable failures, retry rate_limited/timeout)
    # --limit = max NON-PROCESSED videos to add per channel for this run.
    # Manifest is capped at 26 videos/channel (project objective).
    work = []
    for entry in manifest:
        video_ids = entry.get("video_ids", [])[:26]
        count = 0
        for vid in video_ids:
            if vid in avs_existing or vid in processed_ids:
                continue
            work.append((entry, vid))
            count += 1
            if count >= args.limit:
                break

    print(f"Manifest: {len(manifest)} channels")
    print(f"Already in AVS: {len(avs_existing)} transcripts")
    print(f"Already final-processed (ok/whisper_failed): {len(processed_ids)}")
    print(f"To process (incl. retryable rate_limited/timeout/dl_failed): {len(work)} videos")
    print(f"Whisper model: {args.model}")

    if args.dry_run:
        for entry, vid in work[:20]:
            print(f"  #{entry['channel_id']} {entry['name'][:35]:35s} -> {vid}")
        if len(work) > 20:
            print(f"  ... and {len(work) - 20} more")
        return

    if not work:
        print("Nothing to do.")
        return

    # Load Whisper model
    print(f"\nLoading Whisper model '{args.model}' (CPU, int8)...")
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print("Model loaded.")

    # Open shared transcription DB (PRJ-026)
    shared_db = SharedMediaDB()
    print(f"Shared DB: {shared_db.db_path}\n")

    ok_count = 0
    fail_count = 0
    consecutive_rate_limits = 0
    start_time = time.time()

    with tempfile.TemporaryDirectory(prefix="cqi_audio_") as tmpdir:
        for i, (entry, vid) in enumerate(work):
            ch_id = entry["channel_id"]
            ch_name = entry["name"]
            lang_hint = entry.get("language", "en")

            elapsed = time.time() - start_time
            rate = (ok_count + fail_count) / elapsed * 3600 if elapsed > 60 else 0
            eta = (len(work) - i) / (rate / 3600) / 3600 if rate > 0 else 0

            print(f"[{i + 1}/{len(work)}] #{ch_id} {ch_name[:28]:28s} {vid} ",
                  end="", flush=True)
            if rate > 0:
                print(f"({rate:.0f}/h, ETA {eta:.1f}h) ", end="", flush=True)

            # 1. Download audio (only first max_secs via --download-sections)
            audio_path = download_audio(
                vid, tmpdir, max_secs=args.max_secs,
                cookies_path=args.cookies)

            if audio_path == RATE_LIMIT_SENTINEL:
                consecutive_rate_limits += 1
                print(f"RATE_LIMIT ({consecutive_rate_limits} in a row)")
                if consecutive_rate_limits >= args.abort_after_rate_limits:
                    print(f"\n>>> {consecutive_rate_limits} rate-limits in a row. "
                          f"Aborting batch. Resume later with cookies.txt or proxy.")
                    break
                print(f"  Pausing {args.rate_limit_pause:.0f}s before retry...")
                time.sleep(args.rate_limit_pause)
                # Retry same video once after pause
                audio_path = download_audio(
                    vid, tmpdir, max_secs=args.max_secs,
                    cookies_path=args.cookies)
                if audio_path == RATE_LIMIT_SENTINEL or not audio_path \
                        or audio_path == TIMEOUT_SENTINEL:
                    record_progress(db_conn, vid, ch_id, "rate_limited")
                    fail_count += 1
                    continue
                # Retry succeeded — reset counter
                consecutive_rate_limits = 0
            elif audio_path == TIMEOUT_SENTINEL:
                print("TIMEOUT")
                record_progress(db_conn, vid, ch_id, "timeout")
                fail_count += 1
                continue
            elif not audio_path:
                print("DL_FAIL")
                record_progress(db_conn, vid, ch_id, "download_failed")
                fail_count += 1
                # Apply random delay even on fail to avoid pattern
                if i < len(work) - 1:
                    time.sleep(random.uniform(args.min_delay, args.max_delay))
                continue
            else:
                consecutive_rate_limits = 0

            audio_size = os.path.getsize(audio_path) / (1024 * 1024)
            print(f"[{audio_size:.1f}MB] ", end="", flush=True)

            # 2. Transcribe
            transcript, detected_lang = transcribe_audio(
                audio_path, model,
                language=lang_hint if lang_hint != "auto" else None)

            # Delete audio immediately
            try:
                os.remove(audio_path)
            except OSError:
                pass

            if not transcript:
                print("WHISPER_FAIL")
                record_progress(db_conn, vid, ch_id, "whisper_failed")
                fail_count += 1
                continue

            # 2b. Get video title (separate yt-dlp call)
            title = get_video_title(vid)

            # 3. Store in AVS + shared DB
            store_in_avs(vid, title, transcript,
                         detected_lang or lang_hint, ch_name)
            store_in_shared_db(shared_db, vid, title, transcript,
                               detected_lang or lang_hint, ch_name,
                               args.model)

            words = len(transcript.split())
            print(f"OK ({words}w, {detected_lang})")

            record_progress(
                db_conn, vid, ch_id, "ok",
                chars=len(transcript), words=words,
                lang=detected_lang, source="whisper")
            ok_count += 1

            # Random delay between videos (anti bot-pattern)
            if i < len(work) - 1:
                time.sleep(random.uniform(args.min_delay, args.max_delay))

    # Cleanup
    shared_db.close()
    db_conn.close()

    # Summary
    total_elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Done: {ok_count} OK, {fail_count} failed")
    print(f"Time: {total_elapsed / 3600:.1f}h")
    print(f"Total in AVS: {len(get_avs_existing_videos())} transcripts")


if __name__ == "__main__":
    main()
