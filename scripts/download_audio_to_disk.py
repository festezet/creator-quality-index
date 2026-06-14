#!/usr/bin/env python3
"""Phase A : Download YouTube audio to firecuda disk (no re-encode).

Decoupled from transcription : telecharge le format audio natif YouTube
(opus/m4a) sans conversion. Whisper lit ces formats directement via
ffmpeg backend.

Multi-instance support : `--instance N --total T` pour split modulo
les videos a telecharger sur T instances paralleles.

Usage :
    python3 download_audio_to_disk.py --instance 1 --total 3
    python3 download_audio_to_disk.py --instance 2 --total 3
    python3 download_audio_to_disk.py --instance 3 --total 3

Marque DB : status='downloaded', audio_path=<chemin firecuda>.
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared_lib.db import get_connection, query_db, execute_db

# Paths
CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(CQI_ROOT, "data", "video_manifest.json")
CQI_DB_PATH = os.path.join(CQI_ROOT, "data", "benchmark.db")
AUDIO_CACHE = "/data/fcuda_workspace/youtube/audio_cache"

# Defaults
DEFAULT_MIN_DELAY = 5
DEFAULT_MAX_DELAY = 15
DEFAULT_RATE_LIMIT_PAUSE = 600
RATE_LIMIT_SENTINEL = "RATE_LIMIT"
TIMEOUT_SENTINEL = "TIMEOUT"


def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_processed_video_ids(conn):
    """Videos to skip : ok, whisper_failed, downloaded, download_failed."""
    rows = query_db(conn, """
        SELECT video_id FROM download_progress
        WHERE status IN ('ok', 'whisper_failed', 'downloaded', 'download_failed')
    """)
    return {row["video_id"] for row in rows}


def record_progress(conn, video_id, channel_id, status, *, audio_path=None,
                    error_msg=None):
    execute_db(conn, """
        INSERT INTO download_progress
        (video_id, channel_id, status, attempts, error_msg, audio_path)
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            status = excluded.status,
            attempts = download_progress.attempts + 1,
            error_msg = excluded.error_msg,
            audio_path = COALESCE(excluded.audio_path, download_progress.audio_path),
            last_attempt_at = datetime('now')
    """, (video_id, channel_id, status, error_msg, audio_path))


def download_audio(video_id, cookies_path=None, cookies_browser=None, dl_timeout=180):
    """Download native audio (opus/m4a) to AUDIO_CACHE/<video_id>.<ext>.

    Returns:
        - path (str) on success
        - RATE_LIMIT_SENTINEL on bot challenge
        - TIMEOUT_SENTINEL on subprocess timeout
        - None on any other failure
    """
    output_template = os.path.join(AUDIO_CACHE, f"{video_id}.%(ext)s")
    cmd = [
        "/home/fabrice-ryzen/.local/bin/yt-dlp", "--js-runtimes", "node", "--cookies-from-browser", "firefox",
        "-f", "bestaudio",
        "--no-warnings",
        "-o", output_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    if cookies_path and os.path.exists(cookies_path):
        cmd[1:1] = ["--cookies", cookies_path]
    elif cookies_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_browser]

    try:
        print(f'[DEBUG_CMD] {" ".join(cmd)}')
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=dl_timeout,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").lower()
            rate_signals = (
                "http error 429", "too many requests",
                "confirm you're not a bot", "sign in to confirm you're not a bot",
            )
            if any(sig in stderr for sig in rate_signals):
                snippet = (result.stderr or "")[:200].replace("\n", " ")
                print(f"[RATE_LIMIT] {snippet}", flush=True)
                return RATE_LIMIT_SENTINEL
            first_line = (result.stderr or "").split("\n", 1)[0][:200]
            if first_line:
                print(f"[DL_FAIL_ERR] {first_line}", flush=True)
            return None

        # Find downloaded file (extension varies : .opus, .webm, .m4a, etc.)
        for ext in ("opus", "webm", "m4a", "mp4", "mp3"):
            candidate = os.path.join(AUDIO_CACHE, f"{video_id}.{ext}")
            if os.path.exists(candidate):
                return candidate
        # Fallback : glob
        for fname in os.listdir(AUDIO_CACHE):
            if fname.startswith(f"{video_id}."):
                return os.path.join(AUDIO_CACHE, fname)
        return None
    except subprocess.TimeoutExpired:
        return TIMEOUT_SENTINEL
    except OSError as e:
        print(f"[DL_FAIL_OS] {e}", flush=True)
        return None


def main():
    parser = argparse.ArgumentParser(description="Phase A: Download audio to disk")
    parser.add_argument("--instance", type=int, default=1,
                        help="Instance number (1..total) for parallel split")
    parser.add_argument("--total", type=int, default=1,
                        help="Total instances (modulo split)")
    parser.add_argument("--limit", type=int, default=26,
                        help="Max videos per channel (default: 26)")
    parser.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY)
    parser.add_argument("--max-delay", type=float, default=DEFAULT_MAX_DELAY)
    parser.add_argument("--rate-limit-pause", type=float,
                        default=DEFAULT_RATE_LIMIT_PAUSE)
    parser.add_argument("--cookies", default=None,
                        help="Path to Netscape cookies.txt file")
    parser.add_argument("--cookies-from-browser", default=None,
                        help="Browser to extract cookies from (e.g. firefox, chrome)")
    parser.add_argument("--abort-after-rate-limits", type=int, default=3)
    parser.add_argument("--stats", action="store_true",
                        help="Show progress stats and exit")
    args = parser.parse_args()

    db_conn = get_connection(CQI_DB_PATH)

    if args.stats:
        rows = query_db(db_conn, """
            SELECT status, COUNT(*) AS n FROM download_progress GROUP BY status
        """)
        print("download_progress stats:")
        for r in rows:
            print(f"  {r['status']:20s} {r['n']:6d}")
        return

    if not (1 <= args.instance <= args.total):
        print(f"ERROR: --instance must be in [1..{args.total}]")
        sys.exit(2)

    os.makedirs(AUDIO_CACHE, exist_ok=True)
    manifest = load_manifest()
    processed = get_processed_video_ids(db_conn)

    # Build work list (skip already done) + apply modulo split
    work = []
    for entry in manifest:
        ch_id = entry.get("channel_id") or entry.get("id")
        videos = entry.get("video_ids", [])[: args.limit]
        for vid in videos:
            if vid in processed:
                continue
            # Modulo split deterministe (MD5, sinon hash() Python randomise par process)
            h = int(hashlib.md5(vid.encode()).hexdigest()[:8], 16)
            if h % args.total != args.instance - 1:
                continue
            work.append((entry, vid))

    print(f"Instance {args.instance}/{args.total} : {len(work)} videos to download",
          flush=True)
    if not work:
        print("Nothing to do.")
        return

    consecutive_rate_limits = 0
    ok_count = fail_count = 0
    start_time = time.time()

    for i, (entry, vid) in enumerate(work):
        ch_id = entry.get("channel_id") or entry.get("id")
        ch_name = entry.get("name", "?")

        elapsed = time.time() - start_time
        rate = (ok_count + fail_count) / elapsed * 3600 if elapsed > 60 else 0

        print(f"[{i+1}/{len(work)}] #{ch_id} {ch_name[:28]:28s} {vid} ",
              end="", flush=True)
        if rate > 0:
            eta = (len(work) - i) / (rate / 3600) / 3600
            print(f"({rate:.0f}/h, ETA {eta:.1f}h) ", end="", flush=True)

        result = download_audio(
            vid,
            cookies_path=args.cookies,
            cookies_browser=args.cookies_from_browser,
        )

        if result == RATE_LIMIT_SENTINEL:
            consecutive_rate_limits += 1
            print(f"RATE_LIMIT ({consecutive_rate_limits} in a row)", flush=True)
            if consecutive_rate_limits >= args.abort_after_rate_limits:
                print(f"\n>>> {consecutive_rate_limits} rate-limits, aborting.",
                      flush=True)
                break
            print(f"  Pausing {args.rate_limit_pause:.0f}s...", flush=True)
            time.sleep(args.rate_limit_pause)
            record_progress(db_conn, vid, ch_id, "rate_limited")
            fail_count += 1
            continue
        elif result == TIMEOUT_SENTINEL:
            print("TIMEOUT", flush=True)
            record_progress(db_conn, vid, ch_id, "timeout")
            fail_count += 1
            continue
        elif not result:
            print("DL_FAIL", flush=True)
            record_progress(db_conn, vid, ch_id, "download_failed")
            fail_count += 1
            if i < len(work) - 1:
                time.sleep(random.uniform(args.min_delay, args.max_delay))
            continue

        # Success
        consecutive_rate_limits = 0
        size_mb = os.path.getsize(result) / (1024 * 1024)
        print(f"OK ({size_mb:.1f}MB, {os.path.basename(result)})", flush=True)
        record_progress(db_conn, vid, ch_id, "downloaded", audio_path=result)
        ok_count += 1

        if i < len(work) - 1:
            time.sleep(random.uniform(args.min_delay, args.max_delay))

    db_conn.close()
    elapsed = time.time() - start_time
    print(f"\nInstance {args.instance} done : {ok_count} OK, {fail_count} fail "
          f"in {elapsed/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
