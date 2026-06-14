#!/usr/bin/env python3
"""Phase 3 — Score individual video transcripts via AI, store in video_scores.

Reads transcripts from ai-video-studio media/{vid}/transcript.json,
generates scoring prompts, calls AI (Anthropic API / manual), and stores
results in CQI video_scores table + JSON files.

Features:
- Incremental: skips videos already scored in video_scores table
- Reads from ai-video-studio (cross-project transcript store)
- Stores scores in CQI DB (dual SQLite/PostgreSQL via db_adapter)
- JSON backup of each score in data/ai_scores_v2/

Usage:
    python3 batch_score_videos.py [--channel-id ID] [--limit N] [--dry-run]
    python3 batch_score_videos.py --from-json data/ai_scores_v2/  # import existing JSON scores
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db_adapter import db_query, db_execute

# Paths
CQI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(CQI_ROOT, "data", "video_manifest.json")
SCORES_DIR = os.path.join(CQI_ROOT, "data", "ai_scores_v2")
AVS_MEDIA_DIR = "/data/projects/ai-video-studio/data/media"

# Max chars for AI prompt
MAX_TRANSCRIPT_CHARS = 12000

CRITERIA = ["research_depth", "signal_noise", "originality", "lasting_impact"]
SCORE_COLUMNS = ["score_research", "score_signal_noise", "score_originality", "score_lasting_impact"]


def load_manifest():
    """Load video manifest from Phase 1."""
    if not os.path.exists(MANIFEST_PATH):
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        print("Run batch_discover_videos.py first (Phase 1).")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_scored_videos():
    """Get set of (channel_id, video_id) already scored."""
    rows = db_query("SELECT channel_id, video_id FROM video_scores")
    return {(r["channel_id"], r["video_id"]) for r in rows}


def load_transcript(video_id):
    """Load transcript from ai-video-studio media directory.

    Returns:
        (text, language) tuple, or (None, None) if not found.
    """
    transcript_path = os.path.join(AVS_MEDIA_DIR, video_id, "transcript.json")
    if not os.path.exists(transcript_path):
        return None, None
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("text"), data.get("language", "en")


def get_ok_videos(limit_per_channel):
    """Videos to score: status='ok' in download_progress (all have transcripts).

    Source of truth is download_progress, NOT the manifest — substitutions
    appended video_ids beyond the first 26, so manifest[:26] would miss ~40%
    of transcribed videos. Returns dict channel_id -> [video_id, ...] capped
    at limit_per_channel.
    """
    rows = db_query("""
        SELECT channel_id, video_id FROM download_progress
        WHERE status = 'ok'
        ORDER BY channel_id, completed_at
    """)
    by_channel = {}
    for r in rows:
        by_channel.setdefault(r["channel_id"], [])
        if len(by_channel[r["channel_id"]]) < limit_per_channel:
            by_channel[r["channel_id"]].append(r["video_id"])
    return by_channel


def get_channel_names():
    """Channel id -> name mapping from channels table."""
    rows = db_query("SELECT id, name FROM channels")
    return {r["id"]: r["name"] for r in rows}


def build_prompt(channel_name, video_title, transcript_text):
    """Build the scoring prompt for AI analysis."""
    truncated = transcript_text[:MAX_TRANSCRIPT_CHARS]
    return f"""You are an expert YouTube content quality evaluator. Analyze this transcript and score it on 4 criteria (1-10 each).

**Channel**: {channel_name}
**Video**: "{video_title}"

## Scoring Rubrics

### Research Depth
- 9-10: Primary sources, academic papers, expert interviews, original data/proofs
- 7-8: Multiple credible sources, fact-checked, deep subject knowledge
- 5-6: Decent research, relies on secondary sources or surface-level analysis
- 3-4: Minimal sourcing, anecdotal evidence, occasional errors
- 1-2: No sources, speculation as fact

### Signal-to-Noise Ratio
- 9-10: Pure content, no filler, every second adds value
- 7-8: Minimal filler, brief sponsor reads, content-focused
- 5-6: Some padding but acceptable, occasional tangents
- 3-4: Significant filler, clickbait, artificial drama
- 1-2: More filler than content

### Originality
- 9-10: Invented a format, unique framework, genuinely novel approach
- 7-8: Distinct voice, recognizable style, original takes
- 5-6: Competent execution of established format
- 3-4: Derivative, follows trends
- 1-2: Pure repackaging

### Lasting Impact
- 9-10: Timeless content, fundamentally shifts understanding
- 7-8: Mostly evergreen, referenced years later
- 5-6: Good content with some time-sensitivity
- 3-4: Largely time-bound
- 1-2: Disposable content

## Transcript
{truncated}

## Instructions
Return ONLY a JSON object (no markdown, no commentary):
{{"research_depth": X, "signal_noise": X, "originality": X, "lasting_impact": X, "reasoning": {{"research_depth": "...", "signal_noise": "...", "originality": "...", "lasting_impact": "..."}}}}"""


def validate_scores(data):
    """Validate AI response has valid scores.

    Returns:
        Dict with scores if valid, None otherwise.
    """
    if not isinstance(data, dict):
        return None
    for key in CRITERIA:
        val = data.get(key)
        if not isinstance(val, (int, float)) or val < 1 or val > 10:
            return None
    return data


def save_score_json(channel_id, video_id, score_data):
    """Save score to JSON file for backup/audit."""
    os.makedirs(SCORES_DIR, exist_ok=True)
    path = os.path.join(SCORES_DIR, f"score_{channel_id}_{video_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score_data, f, indent=2, ensure_ascii=False)
    return path


def insert_video_score(channel_id, video_id, video_title, transcript_length, scores):
    """Insert a video score into the CQI database."""
    reasoning = scores.get("reasoning", {})
    reasoning_text = json.dumps(reasoning, ensure_ascii=False) if reasoning else ""

    db_execute("""
        INSERT OR REPLACE INTO video_scores
        (channel_id, video_id, video_title, transcript_length,
         score_research, score_signal_noise, score_originality, score_lasting_impact,
         reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        channel_id, video_id, video_title, transcript_length,
        int(scores["research_depth"]),
        int(scores["signal_noise"]),
        int(scores["originality"]),
        int(scores["lasting_impact"]),
        reasoning_text[:2000],
    ])


def import_from_json(scores_dir, dry_run=False):
    """Import scores from existing JSON files in ai_scores_v2/."""
    if not os.path.isdir(scores_dir):
        print(f"ERROR: Directory not found: {scores_dir}")
        return

    scored = get_scored_videos()
    files = sorted(f for f in os.listdir(scores_dir) if f.startswith("score_") and f.endswith(".json"))
    print(f"Found {len(files)} score files in {scores_dir}")

    imported = 0
    skipped = 0
    errors = 0

    for fname in files:
        path = os.path.join(scores_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ERROR reading {fname}: {e}")
            errors += 1
            continue

        channel_id = data.get("channel_id")
        video_id = data.get("video_id")
        if not channel_id or not video_id:
            print(f"  SKIP {fname}: missing channel_id or video_id")
            errors += 1
            continue

        if (channel_id, video_id) in scored:
            skipped += 1
            continue

        validated = validate_scores(data)
        if not validated:
            print(f"  ERROR {fname}: invalid scores")
            errors += 1
            continue

        if dry_run:
            print(f"  DRY #{channel_id} {video_id}: R={data['research_depth']} "
                  f"S={data['signal_noise']} O={data['originality']} I={data['lasting_impact']}")
        else:
            insert_video_score(
                channel_id, video_id,
                data.get("video_title", f"Video {video_id}"),
                data.get("transcript_length", 0),
                data,
            )
        imported += 1

    action = "Would import" if dry_run else "Imported"
    print(f"\n{action}: {imported}, Skipped: {skipped}, Errors: {errors}")


def main():
    parser = argparse.ArgumentParser(description="Score video transcripts for CQI (Phase 3)")
    parser.add_argument("--channel-id", type=int, help="Process single channel by CQI DB id")
    parser.add_argument("--limit", type=int, default=26, help="Max videos per channel (default: 26)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scored")
    parser.add_argument("--from-json", type=str, help="Import scores from JSON directory")
    parser.add_argument("--generate-prompts", action="store_true",
                        help="Generate prompt files for batch processing (no AI call)")
    args = parser.parse_args()

    # Import mode
    if args.from_json:
        import_from_json(args.from_json, dry_run=args.dry_run)
        return

    scored = get_scored_videos()
    ok_videos = get_ok_videos(args.limit)   # source of truth: download_progress
    channel_names = get_channel_names()

    if args.channel_id:
        ok_videos = {args.channel_id: ok_videos.get(args.channel_id, [])}
        if not ok_videos[args.channel_id]:
            print(f"Channel ID {args.channel_id} has no 'ok' transcripts.")
            sys.exit(1)

    # Build work list from transcribed (ok) videos
    work = []
    no_transcript = 0
    for ch_id in sorted(ok_videos.keys()):
        entry = {"channel_id": ch_id, "name": channel_names.get(ch_id, f"#{ch_id}")}
        for vid in ok_videos[ch_id]:
            if (ch_id, vid) in scored:
                continue
            text, lang = load_transcript(vid)
            if not text:
                no_transcript += 1
                continue
            work.append((entry, vid, text, lang))

    print(f"Channels with transcripts: {len(ok_videos)}")
    print(f"Already scored: {len(scored)} videos")
    print(f"No transcript on disk: {no_transcript}")
    print(f"To score: {len(work)} videos")

    if not work:
        print("Nothing to score.")
        return

    # Generate prompts mode (for batch processing)
    if args.generate_prompts:
        prompts_dir = os.path.join(CQI_ROOT, "data", "scoring_prompts")
        os.makedirs(prompts_dir, exist_ok=True)
        for entry, vid, text, lang in work:
            prompt = build_prompt(entry["name"], f"Video {vid}", text)
            prompt_path = os.path.join(prompts_dir, f"prompt_{entry['channel_id']}_{vid}.txt")
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(prompt)
        print(f"\nGenerated {len(work)} prompt files in {prompts_dir}")
        print("Score manually or via batch API, then use --from-json to import.")
        return

    if args.dry_run:
        for entry, vid, text, lang in work[:20]:
            print(f"  #{entry['channel_id']} {entry['name'][:35]:35s} {vid} "
                  f"({len(text)} chars, {lang})")
        if len(work) > 20:
            print(f"  ... and {len(work) - 20} more")
        return

    # Interactive scoring mode (one at a time)
    print(f"\n{'='*60}")
    print("Interactive scoring mode.")
    print("For each video, the prompt will be printed.")
    print("Paste the AI response JSON, then press Enter twice.")
    print(f"{'='*60}\n")

    scored_count = 0
    for i, (entry, vid, text, lang) in enumerate(work):
        ch_id = entry["channel_id"]
        print(f"\n[{i+1}/{len(work)}] #{ch_id} {entry['name']} — {vid}")
        print(f"Transcript: {len(text)} chars, {len(text.split())} words, lang={lang}")

        prompt = build_prompt(entry["name"], f"Video {vid}", text)

        # Save prompt for reference
        prompt_path = os.path.join(SCORES_DIR, f"prompt_{ch_id}_{vid}.txt")
        os.makedirs(SCORES_DIR, exist_ok=True)
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Prompt saved: {prompt_path}")

        print("\nPaste AI response JSON (empty line to skip):")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not line and lines:
                break
            if not line and not lines:
                break
            lines.append(line)

        if not lines:
            print("  Skipped.")
            continue

        response_text = "\n".join(lines).strip()
        if response_text.startswith("```"):
            response_text = "\n".join(
                l for l in response_text.split("\n")
                if not l.strip().startswith("```")
            )

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"  ERROR: invalid JSON — {e}")
            continue

        validated = validate_scores(data)
        if not validated:
            print("  ERROR: scores out of range (must be 1-10)")
            continue

        # Store
        score_data = {
            "channel_id": ch_id,
            "video_id": vid,
            "channel_name": entry["name"],
            "video_title": f"Video {vid}",
            "transcript_length": len(text),
            **data,
        }
        save_score_json(ch_id, vid, score_data)
        insert_video_score(ch_id, vid, f"Video {vid}", len(text), data)

        print(f"  OK: R={data['research_depth']} S={data['signal_noise']} "
              f"O={data['originality']} I={data['lasting_impact']}")
        scored_count += 1

    print(f"\n{'='*60}")
    print(f"Scored: {scored_count}/{len(work)} videos")
    total_scored = len(get_scored_videos())
    print(f"Total in video_scores: {total_scored}")


if __name__ == "__main__":
    main()
