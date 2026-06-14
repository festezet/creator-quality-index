#!/usr/bin/env python3
"""Phase B : Transcribe cached audio files with faster-whisper.

Lit les videos avec status='downloaded' depuis benchmark.db et leur audio
path sur firecuda. Transcribe via Whisper (CPU, int8). Store dans AVS +
shared transcriptions.db. Marque DB status='ok'.

Audio NON supprime apres transcription (re-process possible avec un
meilleur modele plus tard).

Usage :
    python3 whisper_from_cache.py [--model tiny|base|small] [--limit N]
    python3 whisper_from_cache.py --stats
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/data/projects/youtube-transcription")

from shared_lib.db import get_connection, query_db, execute_db
from shared_media_db import SharedMediaDB

# Paths
CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CQI_DB_PATH = os.path.join(CQI_ROOT, "data", "benchmark.db")
AVS_ROOT = "/data/projects/ai-video-studio"
AVS_DB_PATH = os.path.join(AVS_ROOT, "data", "library.db")
AVS_MEDIA_DIR = os.path.join(AVS_ROOT, "data", "media")
SHARED_DB_PATH = "/data/media/youtube/transcriptions.db"

DEFAULT_MODEL = "tiny"
DEFAULT_MAX_SECS = 600  # Trim to 10 min for Whisper


def update_status(conn, video_id, status, *, chars=None, words=None,
                  lang=None, source=None, error_msg=None):
    execute_db(conn, """
        UPDATE download_progress
        SET status = ?, chars = ?, words = ?, lang = ?, source = ?,
            error_msg = ?, last_attempt_at = datetime('now'),
            completed_at = CASE WHEN ? = 'ok' THEN datetime('now') ELSE completed_at END
        WHERE video_id = ?
    """, (status, chars, words, lang, source, error_msg, status, video_id))


def store_in_avs(video_id, title, transcript_text, language, channel_name):
    conn = get_connection(AVS_DB_PATH)
    execute_db(conn, """
        INSERT OR REPLACE INTO library
        (video_id, title, source_url, source_type, has_transcript, language,
         word_count, channel_name, updated_at)
        VALUES (?, ?, ?, 'youtube', 1, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (video_id, title,
          f"https://www.youtube.com/watch?v={video_id}",
          language, len(transcript_text.split()), channel_name))
    conn.close()

    media_dir = os.path.join(AVS_MEDIA_DIR, video_id)
    os.makedirs(media_dir, exist_ok=True)
    transcript_path = os.path.join(media_dir, "transcript.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump({
            "text": transcript_text, "language": language,
            "video_id": video_id, "title": title,
            "channel_name": channel_name, "source": "whisper",
        }, f, ensure_ascii=False, indent=2)


def store_in_shared_db(shared_db, video_id, title, transcript_text,
                       language, channel_name, whisper_model):
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


def get_video_title(video_id):
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
    """Transcribe with faster-whisper. Returns (text, lang) or (None, None)."""
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
        print(f"WHISPER ERROR: {e}", flush=True)
        return None, None


def get_channel_info(conn, channel_id):
    """Get channel name + language hint from CQI channels table."""
    rows = query_db(conn,
        "SELECT name, language FROM channels WHERE id = ?", (channel_id,))
    if rows:
        return rows[0]["name"], rows[0].get("language", "en")
    return f"Channel {channel_id}", "en"


def trim_audio_if_needed(audio_path, max_secs, tmp_dir):
    """If audio > max_secs, trim with ffmpeg stream copy. Returns path to trimmed
    or original audio. Trimmed file is in tmp_dir.
    """
    # Quick duration check via ffprobe
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        if probe.returncode != 0:
            return audio_path
        duration = float(probe.stdout.strip() or 0)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return audio_path

    if duration <= max_secs:
        return audio_path

    # Trim
    ext = os.path.splitext(audio_path)[1]
    trimmed = os.path.join(tmp_dir, f"trim{ext}")
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-t", str(max_secs),
             "-c", "copy", "-loglevel", "error", trimmed],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and os.path.exists(trimmed):
            return trimmed
    except (subprocess.TimeoutExpired, OSError):
        pass
    return audio_path


def main():
    parser = argparse.ArgumentParser(description="Phase B: Whisper from disk cache")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--limit", type=int, default=0,
                        help="Max videos to process (0 = unlimited)")
    parser.add_argument("--max-secs", type=int, default=DEFAULT_MAX_SECS)
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--keep-audio", action="store_true", default=True,
                        help="Keep audio file after transcription (default)")
    parser.add_argument("--delete-audio", action="store_true",
                        help="Delete audio after successful transcription")
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

    # Get downloaded videos awaiting transcription
    rows = query_db(db_conn, """
        SELECT video_id, channel_id, audio_path FROM download_progress
        WHERE status = 'downloaded' AND audio_path IS NOT NULL
        ORDER BY last_attempt_at ASC
    """)
    work = [(r["video_id"], r["channel_id"], r["audio_path"]) for r in rows]
    if args.limit:
        work = work[: args.limit]

    print(f"Whisper model: {args.model}", flush=True)
    print(f"Videos to transcribe: {len(work)}", flush=True)
    if not work:
        return

    print(f"Loading Whisper model '{args.model}' (CPU, int8)...", flush=True)
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print("Model loaded.", flush=True)

    shared_db = SharedMediaDB(SHARED_DB_PATH)

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="cqi_whisper_")

    ok_count = fail_count = 0
    start_time = time.time()

    for i, (vid, ch_id, audio_path) in enumerate(work):
        elapsed = time.time() - start_time
        rate = (ok_count + fail_count) / elapsed * 3600 if elapsed > 60 else 0

        ch_name, lang_hint = get_channel_info(db_conn, ch_id)
        print(f"[{i+1}/{len(work)}] #{ch_id} {ch_name[:28]:28s} {vid} ",
              end="", flush=True)
        if rate > 0:
            eta = (len(work) - i) / (rate / 3600) / 3600
            print(f"({rate:.0f}/h, ETA {eta:.1f}h) ", end="", flush=True)

        if not os.path.exists(audio_path):
            print("MISSING_AUDIO", flush=True)
            update_status(db_conn, vid, "audio_missing",
                          error_msg=f"File not found: {audio_path}")
            fail_count += 1
            continue

        # Trim if needed
        actual_path = trim_audio_if_needed(audio_path, args.max_secs, tmp_dir)
        size_mb = os.path.getsize(actual_path) / (1024 * 1024)
        print(f"[{size_mb:.1f}MB] ", end="", flush=True)

        # Transcribe
        transcript, detected_lang = transcribe_audio(
            actual_path, model,
            language=lang_hint if lang_hint != "auto" else None)

        # Cleanup trimmed temp
        if actual_path != audio_path:
            try:
                os.remove(actual_path)
            except OSError:
                pass

        if not transcript:
            print("WHISPER_FAIL", flush=True)
            update_status(db_conn, vid, "whisper_failed")
            fail_count += 1
            continue

        # Title + store
        title = get_video_title(vid)
        store_in_avs(vid, title, transcript,
                     detected_lang or lang_hint, ch_name)
        store_in_shared_db(shared_db, vid, title, transcript,
                           detected_lang or lang_hint, ch_name, args.model)

        words = len(transcript.split())
        print(f"OK ({words}w, {detected_lang})", flush=True)
        update_status(db_conn, vid, "ok",
                      chars=len(transcript), words=words,
                      lang=detected_lang, source="whisper")
        ok_count += 1

        if args.delete_audio:
            try:
                os.remove(audio_path)
            except OSError:
                pass

    shared_db.close()
    db_conn.close()
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    elapsed = time.time() - start_time
    print(f"\nDone : {ok_count} OK, {fail_count} fail in {elapsed/60:.1f}min",
          flush=True)


if __name__ == "__main__":
    main()
