#!/usr/bin/env python3
"""Batch apply AI analysis scores to the database.

Reads a JSON file of AI scores and applies them to the channels table.
Input format: list of {id, research_depth, signal_noise, originality, lasting_impact, reasoning}

Usage:
    python3 batch_apply_scores.py data/ai_scores.json [--dry-run]
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from shared_lib.db import get_connection, execute_db, query_db


def apply_scores(scores_file, dry_run=False):
    with open(scores_file, "r", encoding="utf-8") as f:
        scores = json.load(f)

    conn = get_connection(DB_PATH)
    now = datetime.now().isoformat()

    applied = 0
    errors = 0
    skipped = 0

    for entry in scores:
        cid = entry.get("id")
        if not cid:
            print(f"  SKIP: no id in entry")
            errors += 1
            continue

        # Validate scores
        required = ["research_depth", "signal_noise", "originality", "lasting_impact"]
        valid = True
        for key in required:
            val = entry.get(key)
            if not isinstance(val, (int, float)) or val < 1 or val > 10:
                print(f"  ERROR #{cid}: invalid {key}={val}")
                valid = False
                break

        if not valid:
            errors += 1
            continue

        # Check if already scored
        existing = query_db(conn, "SELECT ai_score_research FROM channels WHERE id = ?", [cid], one=True)
        if existing and existing["ai_score_research"] is not None:
            skipped += 1
            continue

        reasoning = entry.get("reasoning", {})
        notes = "; ".join(f"{k}: {v}" for k, v in reasoning.items()) if reasoning else ""

        if dry_run:
            print(f"  DRY #{cid}: R={entry['research_depth']} S={entry['signal_noise']} "
                  f"O={entry['originality']} I={entry['lasting_impact']}")
            applied += 1
            continue

        execute_db(conn, """
            UPDATE channels SET
                ai_score_research = ?,
                ai_score_signal_noise = ?,
                ai_score_originality = ?,
                ai_score_lasting_impact = ?,
                ai_analysis_date = ?,
                ai_analysis_notes = ?
            WHERE id = ?
        """, [
            int(entry["research_depth"]),
            int(entry["signal_noise"]),
            int(entry["originality"]),
            int(entry["lasting_impact"]),
            now,
            notes[:500],
            cid,
        ])
        applied += 1

    conn.close()

    action = "Would apply" if dry_run else "Applied"
    print(f"\n{action}: {applied}, Skipped (already scored): {skipped}, Errors: {errors}")
    print(f"Total entries: {len(scores)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 batch_apply_scores.py <scores.json> [--dry-run]")
        print("       python3 batch_apply_scores.py --overwrite <scores.json>")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    overwrite = "--overwrite" in sys.argv
    scores_file = [a for a in sys.argv[1:] if not a.startswith("--")][0]

    if not os.path.exists(scores_file):
        print(f"ERROR: {scores_file} not found")
        sys.exit(1)

    # Backup DB before applying
    if not dry_run:
        import shutil
        bak = DB_PATH + ".bak"
        shutil.copy2(DB_PATH, bak)
        print(f"Backup: {bak}")

    apply_scores(scores_file, dry_run)


if __name__ == "__main__":
    main()
