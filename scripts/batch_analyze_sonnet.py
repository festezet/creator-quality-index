#!/usr/bin/env python3
"""Batch analyze transcripts with Claude Sonnet via parallel Task agents.

This script is designed to be run interactively from a Claude Code session.
It reads the manifest and prompts, then outputs instructions for launching
parallel Sonnet agents.

Usage:
    python3 batch_analyze_sonnet.py                    # Show status and next batch
    python3 batch_analyze_sonnet.py --batch-size 10    # Show next 10 to analyze
    python3 batch_analyze_sonnet.py --status            # Show progress stats
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from shared_lib.db import get_connection, query_db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MANIFEST_FILE = os.path.join(DATA_DIR, "analysis_manifest.json")
PROMPTS_DIR = os.path.join(DATA_DIR, "prompts")
SCORES_DIR = os.path.join(DATA_DIR, "ai_scores")


def get_analyzed_ids():
    """Get IDs of channels already analyzed."""
    conn = get_connection(DB_PATH)
    rows = query_db(conn, "SELECT id FROM channels WHERE ai_score_research IS NOT NULL")
    conn.close()
    return {r["id"] for r in rows}


def get_pending_scores():
    """Get scores already collected but not yet applied to DB."""
    if not os.path.exists(SCORES_DIR):
        return {}
    scores = {}
    for fname in os.listdir(SCORES_DIR):
        if fname.startswith("score_") and fname.endswith(".json"):
            fpath = os.path.join(SCORES_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "id" in data:
                    scores[data["id"]] = data
    return scores


def show_status():
    """Show overall progress."""
    analyzed_ids = get_analyzed_ids()
    pending_scores = get_pending_scores()

    if not os.path.exists(MANIFEST_FILE):
        print("No manifest found. Run batch_generate_prompts.py first.")
        return

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    total = len(manifest)
    in_db = len([m for m in manifest if m["id"] in analyzed_ids])
    scored = len([m for m in manifest if m["id"] in pending_scores and m["id"] not in analyzed_ids])
    remaining = total - in_db - scored

    print(f"Manifest: {total} channels with transcripts")
    print(f"Already in DB: {in_db}")
    print(f"Scored (pending apply): {scored}")
    print(f"Remaining to analyze: {remaining}")

    if scored > 0:
        print(f"\nTo apply pending scores:")
        print(f"  python3 scripts/batch_apply_scores.py data/ai_scores_merged.json")


def get_next_batch(batch_size=5):
    """Get the next batch of channels to analyze."""
    analyzed_ids = get_analyzed_ids()
    pending_scores = get_pending_scores()
    done_ids = analyzed_ids | set(pending_scores.keys())

    if not os.path.exists(MANIFEST_FILE):
        print("No manifest found. Run batch_generate_prompts.py first.")
        return []

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pending = [m for m in manifest if m["id"] not in done_ids]
    batch = pending[:batch_size]

    if not batch:
        print("All channels analyzed!")
        return []

    print(f"Next batch ({len(batch)}/{len(pending)} remaining):\n")
    for m in batch:
        prompt_path = os.path.join(PROMPTS_DIR, m["prompt_file"])
        exists = os.path.exists(prompt_path)
        status = "OK" if exists else "MISSING"
        print(f"  #{m['id']:3d} [{m['tier']}] {m['name'][:40]:40s} prompt={status}")

    return batch


def save_score(channel_id, channel_name, scores_dict):
    """Save a single channel's AI scores to a JSON file."""
    os.makedirs(SCORES_DIR, exist_ok=True)
    scores_dict["id"] = channel_id
    scores_dict["name"] = channel_name
    out_file = os.path.join(SCORES_DIR, f"score_{channel_id}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(scores_dict, f, indent=2, ensure_ascii=False)
    return out_file


def merge_scores():
    """Merge all individual score files into one for batch_apply_scores.py."""
    scores = get_pending_scores()
    if not scores:
        print("No pending scores to merge.")
        return

    merged = list(scores.values())
    out_file = os.path.join(DATA_DIR, "ai_scores_merged.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"Merged {len(merged)} scores to {out_file}")
    return out_file


def main():
    if "--status" in sys.argv:
        show_status()
    elif "--merge" in sys.argv:
        merge_scores()
    else:
        batch_size = 5
        for i, arg in enumerate(sys.argv):
            if arg == "--batch-size" and i + 1 < len(sys.argv):
                batch_size = int(sys.argv[i + 1])
        get_next_batch(batch_size)


if __name__ == "__main__":
    main()
