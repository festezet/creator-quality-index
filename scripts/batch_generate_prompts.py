#!/usr/bin/env python3
"""Generate analysis prompts from pre-fetched transcripts.

Reads all_transcripts.json (output of batch_fetch_all.py) and generates
individual prompt files for Sonnet analysis.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.transcript_analyzer import ANALYSIS_PROMPT, MAX_TRANSCRIPT_CHARS

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TRANSCRIPTS_FILE = os.path.join(DATA_DIR, "all_transcripts.json")
PROMPTS_DIR = os.path.join(DATA_DIR, "prompts")


def main():
    if not os.path.exists(TRANSCRIPTS_FILE):
        print(f"ERROR: {TRANSCRIPTS_FILE} not found. Run batch_fetch_all.py first.")
        sys.exit(1)

    with open(TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
        transcripts = json.load(f)

    os.makedirs(PROMPTS_DIR, exist_ok=True)

    ok_transcripts = [t for t in transcripts if t.get("status") == "ok"]
    skip_existing = "--force" not in sys.argv

    generated = 0
    skipped = 0
    for t in ok_transcripts:
        cid = t["id"]
        prompt_file = os.path.join(PROMPTS_DIR, f"prompt_{cid}.txt")

        if skip_existing and os.path.exists(prompt_file):
            skipped += 1
            continue

        transcript_text = t["transcript"][:MAX_TRANSCRIPT_CHARS]
        prompt = ANALYSIS_PROMPT.format(
            channel_name=t["name"],
            video_title=t.get("video_title", "Unknown"),
            transcript=transcript_text,
        )

        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)
        generated += 1

    print(f"Transcripts: {len(transcripts)} total, {len(ok_transcripts)} OK")
    print(f"Prompts generated: {generated}, skipped (existing): {skipped}")
    print(f"Output: {PROMPTS_DIR}/prompt_<id>.txt")

    # Also generate a manifest for batch processing
    manifest = []
    for t in ok_transcripts:
        manifest.append({
            "id": t["id"],
            "name": t["name"],
            "tier": t.get("tier", "?"),
            "category": t.get("category", "?"),
            "language": t.get("language", "en"),
            "video_id": t.get("video_id"),
            "video_title": t.get("video_title"),
            "transcript_length": t.get("transcript_length", 0),
            "prompt_file": f"prompt_{t['id']}.txt",
        })

    manifest_file = os.path.join(DATA_DIR, "analysis_manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Manifest: {manifest_file} ({len(manifest)} entries)")


if __name__ == "__main__":
    main()
