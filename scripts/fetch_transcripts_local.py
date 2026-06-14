#!/usr/bin/env python3
"""Fetch YouTube transcripts locally for remaining CQI channels.

Adapted from colab_fetch_transcripts.ipynb for local execution.
Uses longer delays and retries to handle intermittent IP blocking.

Usage:
    python3 scripts/fetch_transcripts_local.py [--delay 10] [--limit 50] [--dry-run]
    python3 scripts/fetch_transcripts_local.py --retry-failed  # Retry ip_blocked/no_video entries
"""
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODO_FILE = os.path.join(PROJECT_DIR, "data", "output", "channels_todo_v2.json")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "data", "local_transcripts.json")
MAX_TRANSCRIPT_CHARS = 12000
DEFAULT_DELAY = 10
MAX_CONSECUTIVE_BLOCKS = 5


def get_recent_video_ids(channel_url, count=3):
    """Get recent video IDs from a channel via yt-dlp."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--flat-playlist', f'--playlist-end={count}',
             '--print', '%(id)s', f'{channel_url}/videos'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return [vid for vid in result.stdout.strip().split('\n') if vid]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def search_video_ids(channel_name, category='', count=3):
    """Search YouTube for videos by channel name (fallback for bad URLs)."""
    query = f"{channel_name} {category}".strip()
    try:
        result = subprocess.run(
            ['yt-dlp', f'ytsearch{count}:{query}',
             '--flat-playlist', '--print', '%(id)s'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return [vid for vid in result.stdout.strip().split('\n') if vid]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def get_video_title(video_id):
    """Get video title via yt-dlp."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--print', '%(title)s', '--no-download',
             f'https://www.youtube.com/watch?v={video_id}'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return 'Unknown'


def fetch_transcript(video_id, languages):
    """Fetch transcript, return (text, status)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id, languages=languages)
        text = ' '.join(snippet.text for snippet in transcript)
        return text, 'ok'
    except Exception as e:
        err = str(e).lower()
        if 'blocking' in err or 'ip' in err:
            return None, 'ip_blocked'
        if 'no longer available' in err or 'unavailable' in err:
            return None, 'unavailable'
        if 'no transcript' in err or 'disabled' in err or 'subtitles' in err:
            return None, 'no_transcript'
        return None, 'no_transcript'


def try_channel_transcript(channel_url, channel_name, category, languages, delay):
    """Try channel URL first, then search fallback. Returns (text, status, video_id)."""
    # Try channel URL first
    video_ids = get_recent_video_ids(channel_url)

    # Fallback: search YouTube by channel name
    if not video_ids:
        video_ids = search_video_ids(channel_name, category)
        if video_ids:
            print(f'(search) ', end='', flush=True)

    if not video_ids:
        return None, 'no_video', None

    for i, vid_id in enumerate(video_ids):
        text, status = fetch_transcript(vid_id, languages)
        if status == 'ok' and text:
            return text, 'ok', vid_id
        if status == 'ip_blocked':
            return None, 'ip_blocked', vid_id
        # Try next video (unavailable/no_transcript might be video-specific)
        if i < len(video_ids) - 1:
            time.sleep(2)

    return None, status, video_ids[0]


def check_transcript_quality(text):
    """Detect corrupted transcripts (low unique word ratio)."""
    words = text.lower().split()
    if len(words) < 50:
        return False, 0.0
    unique_ratio = len(set(words)) / len(words)
    return unique_ratio >= 0.20, unique_ratio


def load_results():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(results):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch YouTube transcripts locally")
    parser.add_argument('--delay', type=int, default=DEFAULT_DELAY,
                        help=f"Seconds between requests (default {DEFAULT_DELAY})")
    parser.add_argument('--limit', type=int, default=0, help="Max channels to process (0=all)")
    parser.add_argument('--dry-run', action='store_true', help="Show plan without fetching")
    parser.add_argument('--retry-failed', action='store_true',
                        help="Retry ip_blocked and no_video entries")
    args = parser.parse_args()

    with open(TODO_FILE, encoding="utf-8") as f:
        channels = json.load(f)
    print(f"Channels in todo: {len(channels)}")

    results = load_results()

    if args.retry_failed:
        # Remove failed entries so they get reprocessed
        retry_statuses = {'ip_blocked', 'no_video'}
        removed = [r for r in results if r.get('status') in retry_statuses]
        results = [r for r in results if r.get('status') not in retry_statuses]
        save_results(results)
        print(f"Removed {len(removed)} failed entries for retry")

    done_ids = {r['id'] for r in results}
    to_process = [ch for ch in channels if ch['id'] not in done_ids]

    if args.limit > 0:
        to_process = to_process[:args.limit]

    ok_count = sum(1 for r in results if r.get('status') in ('ok', 'low_quality'))
    print(f"Already done: {len(done_ids)} ({ok_count} OK)")
    print(f"To process: {len(to_process)}")
    print(f"Delay: {args.delay}s between requests")

    if args.dry_run:
        for i, ch in enumerate(to_process[:20]):
            print(f"  [{i+1}] #{ch['id']} {ch['name']} ({ch.get('language', 'en')})")
        if len(to_process) > 20:
            print(f"  ... and {len(to_process)-20} more")
        return

    if not to_process:
        print("Nothing to process!")
        return

    print(f"\nStarting...\n")
    consecutive_blocks = 0
    backoff_time = 30  # Initial backoff on IP block

    for i, ch in enumerate(to_process):
        cid = ch['id']
        lang = ch.get('language') or 'en'
        languages = [lang, 'en'] if lang != 'en' else ['en']
        name = ch['name'][:40]

        print(f'[{i+1}/{len(to_process)}] #{cid} {name:40s} ({lang}) ... ', end='', flush=True)

        cat = ch.get('primary_category', '')
        text, status, video_id = try_channel_transcript(
            ch['url'], ch['name'], cat, languages, args.delay)

        if status == 'ip_blocked':
            consecutive_blocks += 1
            print(f'IP BLOCKED (streak={consecutive_blocks})')

            if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                print(f'\n>>> {MAX_CONSECUTIVE_BLOCKS} consecutive blocks. Stopping.')
                print(f'>>> Progress: {len(results)} processed, {ok_count} OK')
                print(f'>>> Resume: python3 scripts/fetch_transcripts_local.py --retry-failed')
                results.append({'id': cid, 'name': ch['name'], 'language': lang,
                                'tier': ch.get('tier'), 'category': ch.get('primary_category'),
                                'video_id': video_id, 'status': 'ip_blocked'})
                save_results(results)
                sys.exit(1)

            # Exponential backoff with jitter
            wait = backoff_time + random.randint(0, 15)
            print(f'  Waiting {wait}s before retry...', flush=True)
            time.sleep(wait)
            backoff_time = min(backoff_time * 2, 180)

            text, status, video_id = try_channel_transcript(
                ch['url'], ch['name'], cat, languages, args.delay)
            if status == 'ip_blocked':
                print(f'  Still blocked. Saving and moving on.')
                results.append({'id': cid, 'name': ch['name'], 'language': lang,
                                'tier': ch.get('tier'), 'category': ch.get('primary_category'),
                                'video_id': video_id, 'status': 'ip_blocked'})
                save_results(results)
                continue

        if status == 'ok' and text:
            consecutive_blocks = 0
            backoff_time = 30  # Reset backoff

            is_good, ratio = check_transcript_quality(text)
            quality_status = 'ok' if is_good else 'low_quality'
            title = get_video_title(video_id)
            truncated = text[:MAX_TRANSCRIPT_CHARS]
            ok_count += 1

            print(f'OK ({len(text)} chars, q={ratio:.2f}, vid={video_id})')
            results.append({
                'id': cid, 'name': ch['name'],
                'tier': ch.get('tier'), 'category': ch.get('primary_category'),
                'language': lang, 'video_id': video_id, 'video_title': title,
                'transcript': truncated, 'transcript_length': len(text),
                'unique_word_ratio': round(ratio, 3), 'status': quality_status,
            })

            if ok_count % 10 == 0:
                print(f'  >>> {ok_count} transcripts fetched so far')
        else:
            consecutive_blocks = 0
            print(f'{status.upper()} (vid={video_id})')
            results.append({'id': cid, 'name': ch['name'], 'language': lang,
                            'tier': ch.get('tier'), 'category': ch.get('primary_category'),
                            'video_id': video_id, 'status': status})

        save_results(results)
        # Add jitter to delay
        actual_delay = args.delay + random.randint(0, 5)
        time.sleep(actual_delay)

    save_results(results)
    stats = Counter(r.get('status') for r in results)
    print(f'\n{"="*60}')
    print(f'DONE — {len(results)} total processed')
    for s, c in stats.most_common():
        print(f'  {s}: {c}')
    print(f'Saved to {OUTPUT_FILE}')


if __name__ == "__main__":
    main()
