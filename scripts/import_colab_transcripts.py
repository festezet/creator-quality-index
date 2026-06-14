#!/usr/bin/env python3
"""Import Colab transcripts into local all_transcripts.json.

Usage:
    python3 scripts/import_colab_transcripts.py data/colab_transcripts.json [--dry-run]

Merges Colab results into data/all_transcripts.json:
- Updates existing entries (same id) with Colab transcript
- Adds new entries for channels not yet in all_transcripts.json
- Sets source="colab" on all imported entries
- Skips entries with status ip_blocked (Colab failed too)
"""
import json
import os
import sys
from collections import Counter

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_TRANSCRIPTS = os.path.join(PROJECT_DIR, "data", "all_transcripts.json")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_colab_transcripts.py <colab_file> [--dry-run]")
        sys.exit(1)

    colab_path = sys.argv[1]
    if not os.path.isabs(colab_path):
        colab_path = os.path.join(PROJECT_DIR, colab_path)

    dry_run = "--dry-run" in sys.argv

    if not os.path.exists(colab_path):
        print(f"ERROR: {colab_path} not found")
        sys.exit(1)

    colab = load_json(colab_path)
    print(f"Colab results: {len(colab)} entries")

    # Stats on Colab results
    colab_stats = Counter(r.get("status") for r in colab)
    for status, count in colab_stats.most_common():
        print(f"  {status}: {count}")

    # Load existing
    if os.path.exists(ALL_TRANSCRIPTS):
        existing = load_json(ALL_TRANSCRIPTS)
        print(f"\nExisting all_transcripts.json: {len(existing)} entries")
    else:
        existing = []
        print("\nNo existing all_transcripts.json — creating new")

    # Index existing by id
    existing_by_id = {r["id"]: i for i, r in enumerate(existing)}

    updated = 0
    added = 0
    skipped = 0

    for entry in colab:
        cid = entry["id"]
        status = entry.get("status", "")

        # Skip entries where Colab also failed
        if status in ("ip_blocked",):
            skipped += 1
            continue

        # Normalize to match local format
        record = {
            "id": cid,
            "name": entry.get("name", ""),
            "tier": entry.get("tier"),
            "category": entry.get("category"),
            "language": entry.get("language", "en"),
            "video_id": entry.get("video_id"),
            "video_title": entry.get("video_title", ""),
            "transcript": entry.get("transcript", ""),
            "transcript_length": entry.get("transcript_length", 0),
            "status": status,
            "source": "colab",
        }

        # Keep unique_word_ratio if present
        if "unique_word_ratio" in entry:
            record["unique_word_ratio"] = entry["unique_word_ratio"]

        if cid in existing_by_id:
            idx = existing_by_id[cid]
            old_status = existing[idx].get("status", "")
            # Only overwrite if Colab got a better result
            if status in ("ok", "low_quality") and old_status not in ("ok",):
                existing[idx] = record
                updated += 1
            elif status in ("ok", "low_quality") and old_status == "ok":
                # Both OK — keep existing (already have transcript)
                skipped += 1
            else:
                # Colab failed, keep existing
                skipped += 1
        else:
            existing.append(record)
            added += 1

    print(f"\nImport summary:")
    print(f"  Updated (overwritten): {updated}")
    print(f"  Added (new): {added}")
    print(f"  Skipped: {skipped}")
    print(f"  Total after merge: {len(existing)}")

    if dry_run:
        print("\n[DRY RUN] No changes written.")
    else:
        # Backup before writing
        if os.path.exists(ALL_TRANSCRIPTS):
            backup = ALL_TRANSCRIPTS + ".bak"
            save_json(backup, load_json(ALL_TRANSCRIPTS))
            print(f"\nBackup: {backup}")

        save_json(ALL_TRANSCRIPTS, existing)
        print(f"Saved: {ALL_TRANSCRIPTS}")

    # Final stats
    final_stats = Counter(r.get("status") for r in existing)
    print(f"\nFinal status distribution:")
    for s, c in final_stats.most_common():
        print(f"  {s}: {c}")

    with_transcript = sum(1 for r in existing if r.get("status") in ("ok", "low_quality"))
    print(f"\nChannels with usable transcript: {with_transcript}/{len(existing)}")


if __name__ == "__main__":
    main()
