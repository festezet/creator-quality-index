#!/usr/bin/env python3
"""CLI admin for Creator Quality Index."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from backend.config import DB_PATH, WEIGHTS, TIERS, OUTPUT_DIR
from shared_lib.db import get_connection, query_db, execute_db
from backend.services.transcript_analyzer import (
    analyze_channel, parse_ai_response, compare_scores,
)


def compute_score(scores):
    """Compute composite score and tier."""
    composite = round(
        scores["score_research_depth"] * WEIGHTS["research_depth"]
        + scores["score_production"] * WEIGHTS["production"]
        + scores["score_signal_noise"] * WEIGHTS["signal_noise"]
        + scores["score_originality"] * WEIGHTS["originality"]
        + scores["score_lasting_impact"] * WEIGHTS["lasting_impact"],
        2,
    )
    tier = "D"
    for t, threshold in sorted(TIERS.items(), key=lambda x: -x[1]):
        if composite >= threshold:
            tier = t
            break
    return composite, tier


def cmd_add(args):
    """Add a channel."""
    conn = get_connection(DB_PATH)
    try:
        execute_db(conn, """
            INSERT INTO channels (name, url, platform, language, primary_category, description, is_reviewed)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (args.name or args.url, args.url, args.platform, args.lang, args.category, args.description or ""))
        print(f"Added: {args.name or args.url} [{args.category}]")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()


def cmd_score(args):
    """Score a channel interactively."""
    conn = get_connection(DB_PATH)
    ch = query_db(conn, "SELECT * FROM channels WHERE id = ?", (args.id,), one=True)
    if not ch:
        print(f"Channel #{args.id} not found")
        conn.close()
        return

    print(f"\nScoring: {ch['name']} ({ch['url']})")
    print(f"Category: {ch['primary_category']}\n")

    criteria = [
        ("score_research_depth", "Research Depth (1-10)"),
        ("score_production", "Production Quality (1-10)"),
        ("score_signal_noise", "Signal/Noise Ratio (1-10)"),
        ("score_originality", "Originality (1-10)"),
        ("score_lasting_impact", "Lasting Impact (1-10)"),
    ]

    scores = {}
    for field, label in criteria:
        current = ch.get(field)
        prompt = f"  {label}"
        if current:
            prompt += f" [{current}]"
        prompt += ": "
        val = input(prompt).strip()
        if not val and current:
            scores[field] = current
        elif val.isdigit() and 1 <= int(val) <= 10:
            scores[field] = int(val)
        else:
            print(f"  Invalid, keeping {current}")
            scores[field] = current

    if all(v is not None for v in scores.values()):
        composite, tier = compute_score(scores)
        print(f"\n  Composite: {composite} → Tier {tier}")

        notes = input("  Scoring notes: ").strip() or ch.get("scoring_notes", "")

        execute_db(conn, """
            UPDATE channels SET
                score_research_depth = ?, score_production = ?,
                score_signal_noise = ?, score_originality = ?,
                score_lasting_impact = ?, composite_score = ?,
                tier = ?, scoring_notes = ?, is_reviewed = 1,
                updated_at = datetime('now')
            WHERE id = ?
        """, (
            scores["score_research_depth"], scores["score_production"],
            scores["score_signal_noise"], scores["score_originality"],
            scores["score_lasting_impact"], composite, tier, notes, args.id,
        ))
        print(f"  Saved: {ch['name']} → {tier} ({composite})")
    else:
        print("  Incomplete scores, not saved")
    conn.close()


def cmd_unscored(args):
    """List unscored channels."""
    conn = get_connection(DB_PATH)
    rows = query_db(conn, "SELECT id, name, primary_category, url FROM channels WHERE is_reviewed = 0 ORDER BY id")
    conn.close()

    if not rows:
        print("All channels are scored!")
        return

    print(f"\n{len(rows)} unscored channel(s):\n")
    for r in rows:
        print(f"  #{r['id']:3d}  [{r['primary_category']:20s}]  {r['name']}")


def cmd_export(args):
    """Export benchmark to JSON."""
    conn = get_connection(DB_PATH)
    rows = query_db(conn, """
        SELECT c.*, cat.name as category_name
        FROM channels c
        LEFT JOIN categories cat ON c.primary_category = cat.slug
        WHERE is_reviewed = 1
        ORDER BY composite_score DESC
    """)
    conn.close()

    for r in rows:
        if r.get("sample_videos"):
            try:
                r["sample_videos"] = json.loads(r["sample_videos"])
            except (json.JSONDecodeError, TypeError):
                r["sample_videos"] = []

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = args.output or os.path.join(OUTPUT_DIR, "benchmark.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"channels": rows, "count": len(rows)}, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(rows)} channels to {out_path}")


def cmd_stats(args):
    """Show quick stats."""
    conn = get_connection(DB_PATH)

    total = query_db(conn, "SELECT COUNT(*) as c FROM channels", one=True)["c"]
    reviewed = query_db(conn, "SELECT COUNT(*) as c FROM channels WHERE is_reviewed = 1", one=True)["c"]
    tiers = query_db(conn, "SELECT tier, COUNT(*) as c FROM channels WHERE is_reviewed = 1 AND tier IS NOT NULL GROUP BY tier ORDER BY tier")
    avg = query_db(conn, "SELECT ROUND(AVG(composite_score), 2) as avg FROM channels WHERE is_reviewed = 1 AND composite_score IS NOT NULL", one=True)
    cats = query_db(conn, "SELECT primary_category, COUNT(*) as c FROM channels WHERE is_reviewed = 1 GROUP BY primary_category ORDER BY c DESC")
    conn.close()

    print(f"\n{'='*50}")
    print(f"Creator Quality Index — Stats")
    print(f"{'='*50}")
    print(f"Total channels : {total}")
    print(f"Reviewed       : {reviewed}")
    print(f"Average score  : {avg['avg'] if avg else 'N/A'}")
    print(f"\nTier distribution:")
    for t in tiers:
        bar = "█" * t["c"]
        print(f"  {t['tier']}: {t['c']:3d}  {bar}")
    print(f"\nBy category:")
    for c in cats:
        print(f"  {c['primary_category']:25s} {c['c']:3d}")
    print()


def cmd_analyze(args):
    """Analyze channel(s) via AI transcript analysis."""
    conn = get_connection(DB_PATH)

    if args.id:
        channels = query_db(conn, "SELECT * FROM channels WHERE id = ? AND is_reviewed = 1", (args.id,))
    elif args.all:
        channels = query_db(conn, "SELECT * FROM channels WHERE is_reviewed = 1 ORDER BY id")
    else:
        print("Specify --id <channel_id> or --all")
        conn.close()
        return

    if not channels:
        print("No channels found")
        conn.close()
        return

    print(f"\nAnalyzing {len(channels)} channel(s)...\n")

    for ch in channels:
        print(f"--- {ch['name']} (id={ch['id']}) ---")
        data = analyze_channel(ch["name"], ch["url"])
        if not data:
            print(f"  SKIP: no transcript available\n")
            continue

        print(f"  Video: {data['video_title']} ({data['video_id']})")
        print(f"  Transcript: {data['transcript_length']} chars")

        if args.dry_run:
            print(f"  [DRY RUN] Prompt ready ({len(data['prompt'])} chars)")
            if args.compare and ch.get("ai_score_research"):
                _print_comparison(ch)
            print()
            continue

        # Write prompt to temp file for manual AI analysis
        prompt_path = os.path.join(
            os.path.dirname(DB_PATH), "output",
            f"analyze_prompt_{ch['id']}.txt",
        )
        os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(data["prompt"])
        print(f"  Prompt saved: {prompt_path}")
        print(f"  Run AI analysis and pass result with --apply-json")
        print()

    conn.close()


def cmd_analyze_apply(args):
    """Apply AI analysis results to a channel."""
    conn = get_connection(DB_PATH)
    ch = query_db(conn, "SELECT * FROM channels WHERE id = ?", (args.id,), one=True)
    if not ch:
        print(f"Channel #{args.id} not found")
        conn.close()
        return

    try:
        scores = json.loads(args.json)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        conn.close()
        return

    parsed = parse_ai_response(json.dumps(scores))
    if not parsed:
        print("Invalid score format")
        conn.close()
        return

    notes = json.dumps(parsed.get("reasoning", {}), ensure_ascii=False)

    execute_db(conn, """
        UPDATE channels SET
            ai_score_research = ?, ai_score_signal_noise = ?,
            ai_score_originality = ?, ai_score_lasting_impact = ?,
            ai_analysis_date = ?, ai_analysis_notes = ?,
            updated_at = datetime('now')
        WHERE id = ?
    """, (
        int(parsed["research_depth"]), int(parsed["signal_noise"]),
        int(parsed["originality"]), int(parsed["lasting_impact"]),
        datetime.now().isoformat(), notes, args.id,
    ))

    print(f"AI scores saved for {ch['name']}:")
    print(f"  Research:  {parsed['research_depth']}")
    print(f"  Signal:    {parsed['signal_noise']}")
    print(f"  Original:  {parsed['originality']}")
    print(f"  Impact:    {parsed['lasting_impact']}")

    if args.compare:
        comparison = compare_scores(dict(ch), parsed)
        _print_comparison_data(ch["name"], comparison)

    conn.close()


def cmd_analyze_compare(args):
    """Compare AI vs manual scores for all analyzed channels."""
    conn = get_connection(DB_PATH)
    rows = query_db(conn, """
        SELECT * FROM channels
        WHERE is_reviewed = 1 AND ai_score_research IS NOT NULL
        ORDER BY composite_score DESC
    """)
    conn.close()

    if not rows:
        print("No channels have AI analysis yet.")
        return

    print(f"\n{'Channel':30s} {'Criterion':15s} {'Manual':>6s} {'AI':>4s} {'Delta':>6s}")
    print("-" * 65)

    total_delta = 0
    total_count = 0

    for ch in rows:
        criteria = [
            ("Research", ch.get("score_research_depth"), ch.get("ai_score_research")),
            ("Signal", ch.get("score_signal_noise"), ch.get("ai_score_signal_noise")),
            ("Original", ch.get("score_originality"), ch.get("ai_score_originality")),
            ("Impact", ch.get("score_lasting_impact"), ch.get("ai_score_lasting_impact")),
        ]
        first = True
        for name, manual, ai in criteria:
            if manual is not None and ai is not None:
                delta = ai - manual
                label = ch["name"][:29] if first else ""
                print(f"{label:30s} {name:15s} {manual:6d} {ai:4d} {delta:+6d}")
                total_delta += abs(delta)
                total_count += 1
                first = False
        print()

    if total_count:
        print(f"Average absolute delta: {total_delta / total_count:.2f}")


def _print_comparison_data(channel_name, comparison):
    """Print formatted comparison data."""
    print(f"\n  Comparison for {channel_name}:")
    for key, vals in comparison["criteria"].items():
        print(f"    {key:20s}  Manual={vals['manual']}  AI={vals['ai']}  Delta={vals['delta']:+d}")
    if comparison["avg_absolute_delta"] is not None:
        print(f"    Avg absolute delta: {comparison['avg_absolute_delta']}")


def main():
    parser = argparse.ArgumentParser(description="Creator Quality Index CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a channel")
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--name", default=None)
    p_add.add_argument("--category", required=True)
    p_add.add_argument("--lang", default="en")
    p_add.add_argument("--platform", default="youtube")
    p_add.add_argument("--description", default=None)

    p_score = sub.add_parser("score", help="Score a channel (interactive)")
    p_score.add_argument("--id", type=int, required=True)

    sub.add_parser("unscored", help="List unscored channels")

    p_export = sub.add_parser("export", help="Export to JSON")
    p_export.add_argument("--output", default=None)

    sub.add_parser("stats", help="Show stats")

    p_analyze = sub.add_parser("analyze", help="AI transcript analysis")
    p_analyze.add_argument("--id", type=int, help="Channel ID to analyze")
    p_analyze.add_argument("--all", action="store_true", help="Analyze all reviewed channels")
    p_analyze.add_argument("--dry-run", action="store_true", help="Preview without AI call")
    p_analyze.add_argument("--compare", action="store_true", help="Show comparison with manual scores")

    p_apply = sub.add_parser("analyze-apply", help="Apply AI analysis JSON to a channel")
    p_apply.add_argument("--id", type=int, required=True, help="Channel ID")
    p_apply.add_argument("--json", required=True, help="JSON string with AI scores")
    p_apply.add_argument("--compare", action="store_true", help="Show comparison")

    sub.add_parser("analyze-compare", help="Compare AI vs manual scores")

    args = parser.parse_args()
    cmds = {
        "add": cmd_add, "score": cmd_score, "unscored": cmd_unscored,
        "export": cmd_export, "stats": cmd_stats,
        "analyze": cmd_analyze, "analyze-apply": cmd_analyze_apply,
        "analyze-compare": cmd_analyze_compare,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
