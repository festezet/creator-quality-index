#!/usr/bin/env python3
"""CLI admin for Creator Quality Index."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH, WEIGHTS, TIERS, OUTPUT_DIR
from shared_lib.db import get_connection, query_db, execute_db


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

    args = parser.parse_args()
    cmds = {"add": cmd_add, "score": cmd_score, "unscored": cmd_unscored, "export": cmd_export, "stats": cmd_stats}
    cmds[args.command](args)


if __name__ == "__main__":
    main()
