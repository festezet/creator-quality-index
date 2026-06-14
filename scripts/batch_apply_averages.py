#!/usr/bin/env python3
"""Phase 3b — Compute per-channel score aggregates from video_scores.

Reads individual video scores from the video_scores table, computes the
MEDIAN score per criterion per channel (robust to outlier videos), derives
an AI composite (4 criteria, Production excluded) + tier, and tags each
channel with a validity status:
    >= 20 videos -> 'confirmed'
    10-19 videos -> 'provisional'
    <  10 videos -> no AI score written

Production is surfaced separately as ai_score_production_badge (copied from
the manual editorial score), never folded into the AI composite.

Usage:
    python3 batch_apply_averages.py [--dry-run] [--channel-id ID]
    python3 batch_apply_averages.py --stats
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import (
    WEIGHTS_AI, TIERS, AI_SCORE_CONFIRMED_MIN, AI_SCORE_PROVISIONAL_MIN,
)
from backend.db_adapter import db_query, db_execute

# Map video_scores column -> channels AI column + WEIGHTS_AI key
CRITERIA = [
    ("score_research", "ai_score_research", "research_depth"),
    ("score_signal_noise", "ai_score_signal_noise", "signal_noise"),
    ("score_originality", "ai_score_originality", "originality"),
    ("score_lasting_impact", "ai_score_lasting_impact", "lasting_impact"),
]


def compute_ai_composite(medians):
    """Weighted AI composite from the 4 criterion medians (1-10 scale)."""
    total = 0.0
    for _, _, weight_key in CRITERIA:
        col = next(c[0] for c in CRITERIA if c[2] == weight_key)
        val = medians.get(col)
        if val is None:
            return None
        total += val * WEIGHTS_AI[weight_key]
    return round(total, 2)


def compute_tier(composite):
    """Tier letter from composite, shared thresholds with manual scores."""
    if composite is None:
        return None
    for tier, threshold in sorted(TIERS.items(), key=lambda x: -x[1]):
        if composite >= threshold:
            return tier
    return "D"


def score_status(count):
    """Validity status from number of scored videos."""
    if count >= AI_SCORE_CONFIRMED_MIN:
        return "confirmed"
    if count >= AI_SCORE_PROVISIONAL_MIN:
        return "provisional"
    return None


def get_channel_scores():
    """Get aggregated scores per channel from video_scores table.

    Returns:
        Dict of channel_id -> {scores: [...], medians: {...}, count: int}
    """
    rows = db_query("""
        SELECT channel_id, score_research, score_signal_noise,
               score_originality, score_lasting_impact
        FROM video_scores
        ORDER BY channel_id
    """)

    channels = {}
    for row in rows:
        ch_id = row["channel_id"]
        if ch_id not in channels:
            channels[ch_id] = {"scores": [], "count": 0}
        channels[ch_id]["scores"].append({
            "score_research": row["score_research"],
            "score_signal_noise": row["score_signal_noise"],
            "score_originality": row["score_originality"],
            "score_lasting_impact": row["score_lasting_impact"],
        })
        channels[ch_id]["count"] += 1

    # Compute medians (robust to outlier videos)
    for ch_id, data in channels.items():
        medians = {}
        for col, _, _ in CRITERIA:
            values = [s[col] for s in data["scores"] if s[col] is not None]
            medians[col] = round(statistics.median(values), 1) if values else None
        data["medians"] = medians

    return channels


def get_channel_names():
    """Get channel id -> (name, manual production score) mapping."""
    rows = db_query("SELECT id, name, score_production FROM channels")
    return {r["id"]: {"name": r["name"], "production": r["score_production"]}
            for r in rows}


def apply_averages(channel_scores, channel_meta, dry_run=False, channel_id=None):
    """Apply median AI scores + composite + tier + status to channels.

    Only channels with >= AI_SCORE_PROVISIONAL_MIN videos get an AI score
    written. Production is copied verbatim from the manual score as a badge.

    Args:
        channel_scores: Output of get_channel_scores().
        channel_meta: Dict of channel_id -> {name, production}.
        dry_run: If True, show what would be applied without modifying DB.
        channel_id: If set, only apply to this channel.
    """
    applied_confirmed = 0
    applied_provisional = 0
    skipped_low = 0
    skipped_missing = 0

    targets = [channel_id] if channel_id else sorted(channel_scores.keys())

    for ch_id in targets:
        meta = channel_meta.get(ch_id, {"name": f"Unknown #{ch_id}", "production": None})
        name = meta["name"]

        if ch_id not in channel_scores:
            skipped_missing += 1
            continue

        data = channel_scores[ch_id]
        count = data["count"]
        medians = data["medians"]
        status = score_status(count)

        if status is None:
            if dry_run:
                print(f"  SKIP #{ch_id} {name[:38]:38s} — {count} videos "
                      f"(< {AI_SCORE_PROVISIONAL_MIN})")
            skipped_low += 1
            continue

        r = medians.get("score_research")
        s = medians.get("score_signal_noise")
        o = medians.get("score_originality")
        i = medians.get("score_lasting_impact")
        composite = compute_ai_composite(medians)
        tier = compute_tier(composite)
        prod = meta["production"]

        if dry_run:
            flag = "✓" if status == "confirmed" else "~"
            print(f"  {flag} #{ch_id:3d} {name[:34]:34s} ({count:2d}v) "
                  f"R={r} S={s} O={o} I={i} -> {composite} [{tier}] {status}")
        else:
            db_execute("""
                UPDATE channels SET
                    ai_score_research = ?,
                    ai_score_signal_noise = ?,
                    ai_score_originality = ?,
                    ai_score_lasting_impact = ?,
                    ai_composite_score = ?,
                    ai_tier = ?,
                    ai_score_status = ?,
                    ai_score_production_badge = ?,
                    ai_videos_scored = ?,
                    ai_analysis_date = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [
                int(round(r)) if r is not None else None,
                int(round(s)) if s is not None else None,
                int(round(o)) if o is not None else None,
                int(round(i)) if i is not None else None,
                composite, tier, status, prod, count, ch_id,
            ])

        if status == "confirmed":
            applied_confirmed += 1
        else:
            applied_provisional += 1

    return applied_confirmed, applied_provisional, skipped_low, skipped_missing


def main():
    parser = argparse.ArgumentParser(description="Apply video score medians + AI composite to channels (Phase 3b)")
    parser.add_argument("--dry-run", action="store_true", help="Show aggregates without applying")
    parser.add_argument("--channel-id", type=int, help="Apply to single channel")
    parser.add_argument("--stats", action="store_true", help="Show scoring coverage stats only")
    args = parser.parse_args()

    channel_scores = get_channel_scores()
    channel_meta = get_channel_names()

    if args.stats:
        total_channels = len(channel_meta)
        scored_channels = len(channel_scores)
        total_videos = sum(d["count"] for d in channel_scores.values())
        confirmed = sum(1 for d in channel_scores.values() if d["count"] >= AI_SCORE_CONFIRMED_MIN)
        provisional = sum(1 for d in channel_scores.values()
                          if AI_SCORE_PROVISIONAL_MIN <= d["count"] < AI_SCORE_CONFIRMED_MIN)
        too_few = sum(1 for d in channel_scores.values() if 0 < d["count"] < AI_SCORE_PROVISIONAL_MIN)

        print(f"Channels: {total_channels} total, {scored_channels} with video scores")
        print(f"Videos scored: {total_videos}")
        print(f"Confirmed (>= {AI_SCORE_CONFIRMED_MIN}): {confirmed}")
        print(f"Provisional ({AI_SCORE_PROVISIONAL_MIN}-{AI_SCORE_CONFIRMED_MIN-1}): {provisional}")
        print(f"Too few (< {AI_SCORE_PROVISIONAL_MIN}, no AI score): {too_few}")
        print(f"None: {total_channels - scored_channels}")

        # Distribution
        buckets = {"0": 0, "1-9": 0, "10-19": 0, "20-25": 0, "26+": 0}
        for ch_id in channel_meta:
            count = channel_scores.get(ch_id, {}).get("count", 0)
            if count == 0:
                buckets["0"] += 1
            elif count < 10:
                buckets["1-9"] += 1
            elif count < 20:
                buckets["10-19"] += 1
            elif count <= 25:
                buckets["20-25"] += 1
            else:
                buckets["26+"] += 1

        print("\nDistribution:")
        for bucket, count in buckets.items():
            print(f"  {bucket:>6s}: {count:3d} {'#' * count}")
        return

    if not channel_scores:
        print("No video scores found. Run batch_score_videos.py first (Phase 3).")
        return

    print(f"Channels with video scores: {len(channel_scores)}")
    print(f"Thresholds: confirmed >= {AI_SCORE_CONFIRMED_MIN}, "
          f"provisional >= {AI_SCORE_PROVISIONAL_MIN} (median aggregation)")

    if args.dry_run:
        print("\n--- DRY RUN ---")

    confirmed, provisional, skipped_low, skipped_missing = apply_averages(
        channel_scores, channel_meta,
        dry_run=args.dry_run,
        channel_id=args.channel_id,
    )

    action = "Would apply" if args.dry_run else "Applied"
    print(f"\n{'='*60}")
    print(f"{action}: {confirmed} confirmed + {provisional} provisional")
    print(f"Skipped (< {AI_SCORE_PROVISIONAL_MIN} videos): {skipped_low}")
    if skipped_missing:
        print(f"Skipped (no scores): {skipped_missing}")


if __name__ == "__main__":
    main()
