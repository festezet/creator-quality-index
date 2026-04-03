#!/usr/bin/env python3
"""Migrate data from local SQLite to PostgreSQL on Render.

Usage:
    DATABASE_URL=postgresql://... python3 scripts/migrate_to_pg.py
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH, DATABASE_URL

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Export it first.")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. pip install psycopg2-binary")
    sys.exit(1)


def get_sqlite_data():
    """Read all channels and categories from local SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cats = [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY sort_order")]
    channels = [dict(r) for r in conn.execute("SELECT * FROM channels")]
    conn.close()

    print(f"SQLite: {len(cats)} categories, {len(channels)} channels")
    return cats, channels


def migrate(cats, channels):
    """Insert data into PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Ensure schema exists
    from backend.init_pg import PG_SCHEMA
    cur.execute(PG_SCHEMA)
    conn.commit()

    # Insert categories
    cat_count = 0
    for c in cats:
        cur.execute(
            "INSERT INTO categories (slug, name, icon, sort_order) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (slug) DO NOTHING",
            (c["slug"], c["name"], c.get("icon"), c.get("sort_order", 0)),
        )
        cat_count += cur.rowcount
    conn.commit()
    print(f"PostgreSQL: inserted {cat_count} new categories")

    # Insert channels
    ch_count = 0
    for ch in channels:
        # sample_videos may be JSON string or None
        sample_videos = ch.get("sample_videos")
        if sample_videos and isinstance(sample_videos, str):
            try:
                json.loads(sample_videos)
            except (json.JSONDecodeError, TypeError):
                sample_videos = json.dumps([sample_videos])

        cur.execute("""
            INSERT INTO channels (
                channel_id, name, url, platform, language, primary_category,
                description, subscriber_count, total_views, video_count,
                avg_upload_frequency_days,
                score_research_depth, score_production, score_signal_noise,
                score_originality, score_lasting_impact,
                composite_score, tier, scoring_notes, sample_videos,
                is_reviewed, is_featured
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (channel_id) DO NOTHING
        """, (
            ch.get("channel_id"), ch["name"], ch["url"],
            ch.get("platform", "youtube"), ch.get("language", "en"),
            ch["primary_category"], ch.get("description"),
            ch.get("subscriber_count"), ch.get("total_views"),
            ch.get("video_count"), ch.get("avg_upload_frequency_days"),
            ch.get("score_research_depth"), ch.get("score_production"),
            ch.get("score_signal_noise"), ch.get("score_originality"),
            ch.get("score_lasting_impact"), ch.get("composite_score"),
            ch.get("tier"), ch.get("scoring_notes"), sample_videos,
            bool(ch.get("is_reviewed")), bool(ch.get("is_featured")),
        ))
        ch_count += cur.rowcount

    conn.commit()
    print(f"PostgreSQL: inserted {ch_count} new channels")

    # Verify counts
    cur.execute("SELECT COUNT(*) FROM categories")
    pg_cats = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM channels")
    pg_channels = cur.fetchone()[0]
    print(f"PostgreSQL totals: {pg_cats} categories, {pg_channels} channels")

    cur.close()
    conn.close()


if __name__ == "__main__":
    cats, channels = get_sqlite_data()
    migrate(cats, channels)
    print("Migration complete!")
