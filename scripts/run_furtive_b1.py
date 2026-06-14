#!/usr/bin/env python3
"""Furtive batch runner for B1 strategy.

Runs batch_whisper_transcripts.py in small sub-batches with long pauses,
randomized channel order, conservative anti-bot delays.

Usage:
    python3 scripts/run_furtive_b1.py [--sub-batch N] [--pause SEC] [--max-batches N]
"""
import argparse
import functools
import os
import random
import subprocess
import sys
import time

# Force unbuffered prints so stdout-redirected log gets written in real time.
print = functools.partial(print, flush=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared_lib.db import get_connection, query_db

CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(CQI_ROOT, "data", "benchmark.db")
SCRIPT_PATH = os.path.join(CQI_ROOT, "scripts", "batch_whisper_transcripts.py")
LOG_DIR = os.path.join(CQI_ROOT, "data", "output")


class _Tee:
    """Tee stdout into a log file in addition to the original stream."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        if isinstance(data, str):
            for s in self.streams:
                if hasattr(s, "buffer"):
                    s.write(data)
                else:
                    s.write(data.encode())
                if hasattr(s, "flush"):
                    s.flush()
        else:
            for s in self.streams:
                if hasattr(s, "buffer"):
                    s.buffer.write(data)
                else:
                    s.write(data)
                if hasattr(s, "flush"):
                    s.flush()

    def flush(self):
        for s in self.streams:
            if hasattr(s, "flush"):
                s.flush()


def get_channels_with_failed(conn):
    """Return list of (channel_id, n_failed) ordered by channel_id."""
    rows = query_db(conn, """
        SELECT channel_id, COUNT(*) AS n
        FROM download_progress
        WHERE status='download_failed'
        GROUP BY channel_id
        HAVING n > 0
        ORDER BY channel_id
    """)
    return [(r["channel_id"], r["n"]) for r in rows]


def get_global_stats(conn):
    rows = query_db(conn,
                    "SELECT status, COUNT(*) AS n FROM download_progress GROUP BY status")
    return {r["status"]: r["n"] for r in rows}


def run_channel(channel_id, limit, min_delay, max_delay, max_secs, log_path):
    cmd = [
        "python3", SCRIPT_PATH,
        "--channel-id", str(channel_id),
        "--limit", str(limit),
        "--min-delay", str(min_delay),
        "--max-delay", str(max_delay),
        "--max-secs", str(max_secs),
        "--model", "tiny",
    ]
    print(f"  $ {' '.join(cmd)}")
    with open(log_path, "ab") as f:
        f.write(f"\n\n===== Channel {channel_id} (limit={limit}) =====\n".encode())
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                                cwd=CQI_ROOT, timeout=3600)
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sub-batch", type=int, default=3,
                        help="Channels per sub-batch (default: 3)")
    parser.add_argument("--limit", type=int, default=10,
                        help="Videos per channel per sub-batch (default: 10)")
    parser.add_argument("--pause", type=int, default=300,
                        help="Pause between sub-batches in seconds (default: 300)")
    parser.add_argument("--min-delay", type=float, default=30,
                        help="Min delay between videos (default: 30s)")
    parser.add_argument("--max-delay", type=float, default=90,
                        help="Max delay between videos (default: 90s)")
    parser.add_argument("--max-secs", type=int, default=300,
                        help="Audio duration cap (default: 300s)")
    parser.add_argument("--max-batches", type=int, default=None,
                        help="Stop after N sub-batches (default: until done)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without running")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"b1_furtive_{int(time.time())}.log")
    runner_event_log = os.path.join(LOG_DIR, f"b1_events_{int(time.time())}.log")
    print(f"Log file (subprocess output) : {log_path}")
    print(f"Event log (wrapper progress) : {runner_event_log}")
    # Mirror stdout to a dedicated event log for crash forensics.
    sys.stdout = _Tee(sys.stdout, open(runner_event_log, "ab"))
    print(f"Sub-batch size: {args.sub_batch} channels x {args.limit} videos = "
          f"{args.sub_batch * args.limit} videos/batch")
    print(f"Delay per video: {args.min_delay}-{args.max_delay}s "
          f"(avg {(args.min_delay + args.max_delay) / 2:.0f}s)")
    print(f"Pause between batches: {args.pause}s")
    print()

    batch_num = 0
    while True:
        conn = get_connection(DB_PATH)
        channels = get_channels_with_failed(conn)
        stats = get_global_stats(conn)
        conn.close()

        if not channels:
            print(f"\n>>> All channels processed. Final stats: {stats}")
            break

        if args.max_batches and batch_num >= args.max_batches:
            print(f"\n>>> Reached max-batches={args.max_batches}. Stopping.")
            break

        batch_num += 1
        # Random channel order
        random.shuffle(channels)
        sub_batch = channels[:args.sub_batch]

        total_failed = sum(n for _, n in channels)
        print(f"━━━ Sub-batch #{batch_num} ━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Remaining: {len(channels)} channels, {total_failed} failed videos")
        print(f"Stats: {stats}")
        print(f"This batch: channels {[c for c, _ in sub_batch]}")

        if args.dry_run:
            for ch_id, n in sub_batch:
                print(f"  Would run channel {ch_id} (limit={args.limit}, has {n} failed)")
            return

        batch_start = time.time()
        for ch_id, n_failed in sub_batch:
            print(f"\n>>> Channel {ch_id} ({n_failed} failed)")
            try:
                rc = run_channel(ch_id, args.limit,
                                 args.min_delay, args.max_delay,
                                 args.max_secs, log_path)
                if rc != 0:
                    print(f"  WARN: channel {ch_id} returned rc={rc}")
            except subprocess.TimeoutExpired:
                print(f"  ERROR: channel {ch_id} subprocess timed out (>1h)")
            except KeyboardInterrupt:
                print("\n>>> Interrupted by user.")
                return

        batch_dur = time.time() - batch_start
        print(f"\nSub-batch #{batch_num} done in {batch_dur / 60:.1f} min")

        # Re-stats
        conn = get_connection(DB_PATH)
        new_stats = get_global_stats(conn)
        new_channels = get_channels_with_failed(conn)
        conn.close()
        delta_ok = new_stats.get("ok", 0) - stats.get("ok", 0)
        delta_failed = new_stats.get("download_failed", 0) - stats.get("download_failed", 0)
        delta_rl = new_stats.get("rate_limited", 0) - stats.get("rate_limited", 0)
        delta_to = new_stats.get("timeout", 0) - stats.get("timeout", 0)
        print(f"Delta: +{delta_ok} ok, {delta_failed:+d} failed, "
              f"{delta_rl:+d} rate_limited, {delta_to:+d} timeout")
        print(f"Stats now: {new_stats}")

        # Abort guard: if rate_limited grew significantly
        if delta_rl >= 5:
            print(f"\n>>> {delta_rl} rate_limited in last batch. "
                  f"Pausing 30 min before continuing.")
            time.sleep(1800)
        elif new_channels and (args.max_batches is None or batch_num < args.max_batches):
            print(f"Pausing {args.pause}s before next sub-batch...")
            time.sleep(args.pause)


if __name__ == "__main__":
    sys.exit(main())
