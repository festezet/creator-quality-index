#!/usr/bin/env python3
"""Merge individual AI score JSON files into one batch file for batch_apply_scores.py.

Reads data/ai_scores/scores_*.json and outputs data/ai_scores_batch.json.

Usage:
    python3 scripts/merge_ai_scores.py [--dry-run]
"""
import json
import glob
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SCORES_DIR = os.path.join(DATA_DIR, "ai_scores")
OUTPUT = os.path.join(DATA_DIR, "ai_scores_batch.json")


def main():
    dry_run = "--dry-run" in sys.argv
    files = sorted(glob.glob(os.path.join(SCORES_DIR, "scores_*.json")))

    if not files:
        print("No score files found in", SCORES_DIR)
        sys.exit(1)

    all_scores = []
    errors = 0

    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            cid = data.get("channel_id") or data.get("id")
            if not cid:
                print(f"  WARN: no id in {os.path.basename(fpath)}")
                errors += 1
                continue

            entry = {
                "id": cid,
                "research_depth": data.get("research_depth"),
                "signal_noise": data.get("signal_noise"),
                "originality": data.get("originality"),
                "lasting_impact": data.get("lasting_impact"),
                "reasoning": data.get("reasoning", {}),
            }
            all_scores.append(entry)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ERROR: {os.path.basename(fpath)}: {e}")
            errors += 1

    print(f"Merged: {len(all_scores)} scores from {len(files)} files ({errors} errors)")

    if dry_run:
        for s in all_scores:
            print(f"  #{s['id']}: R={s['research_depth']} S={s['signal_noise']} "
                  f"O={s['originality']} I={s['lasting_impact']}")
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_scores, f, indent=2, ensure_ascii=False)
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
