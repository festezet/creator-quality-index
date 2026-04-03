"""Initialize the benchmark database."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH, DATA_DIR
from shared_lib.db import get_connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT UNIQUE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    platform TEXT DEFAULT 'youtube',
    language TEXT DEFAULT 'en',
    primary_category TEXT NOT NULL REFERENCES categories(slug),
    description TEXT,

    subscriber_count INTEGER,
    total_views INTEGER,
    video_count INTEGER,
    avg_upload_frequency_days REAL,

    score_research_depth INTEGER CHECK(score_research_depth BETWEEN 1 AND 10),
    score_production INTEGER CHECK(score_production BETWEEN 1 AND 10),
    score_signal_noise INTEGER CHECK(score_signal_noise BETWEEN 1 AND 10),
    score_originality INTEGER CHECK(score_originality BETWEEN 1 AND 10),
    score_lasting_impact INTEGER CHECK(score_lasting_impact BETWEEN 1 AND 10),

    composite_score REAL,
    tier TEXT CHECK(tier IN ('S','A','B','C','D')),

    scoring_notes TEXT,
    sample_videos TEXT,
    is_reviewed INTEGER DEFAULT 0,
    is_featured INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_channels_category ON channels(primary_category);
CREATE INDEX IF NOT EXISTS idx_channels_tier ON channels(tier);
CREATE INDEX IF NOT EXISTS idx_channels_composite ON channels(composite_score DESC);

CREATE TABLE IF NOT EXISTS community_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL,
    criterion TEXT NOT NULL,
    score INTEGER CHECK(score BETWEEN 1 AND 10),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(channel_id, visitor_id, criterion)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES comments(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL,
    visitor_name TEXT DEFAULT 'Anonymous',
    content TEXT NOT NULL,
    upvotes INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    is_visible INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_ratings_channel ON community_ratings(channel_id);
CREATE INDEX IF NOT EXISTS idx_comments_channel ON comments(channel_id);
"""

CATEGORIES = [
    ("science", "Science", "🔬", 1),
    ("tech-dev", "Tech & Development", "💻", 2),
    ("engineering", "Engineering", "⚙️", 3),
    ("finance", "Finance & Economics", "📈", 4),
    ("history", "History", "📜", 5),
    ("geopolitics", "Geopolitics", "🌍", 6),
    ("productivity", "Productivity", "⚡", 7),
    ("philosophy-essays", "Philosophy & Essays", "💭", 8),
    ("design-art", "Design & Art", "🎨", 9),
    ("education", "Education", "📚", 10),
    ("environment", "Environment", "🌱", 11),
    ("making", "Making & DIY", "🔧", 12),
]


def init_db():
    """Create tables and seed categories."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_connection(DB_PATH)
    conn.executescript(SCHEMA)

    for slug, name, icon, sort_order in CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories (slug, name, icon, sort_order) VALUES (?, ?, ?, ?)",
            (slug, name, icon, sort_order),
        )
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")
    print(f"  {len(CATEGORIES)} categories seeded")


COMMUNITY_TABLES = """
CREATE TABLE IF NOT EXISTS community_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL,
    criterion TEXT NOT NULL,
    score INTEGER CHECK(score BETWEEN 1 AND 10),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(channel_id, visitor_id, criterion)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES comments(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL,
    visitor_name TEXT DEFAULT 'Anonymous',
    content TEXT NOT NULL,
    upvotes INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    is_visible INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_ratings_channel ON community_ratings(channel_id);
CREATE INDEX IF NOT EXISTS idx_comments_channel ON comments(channel_id);
"""


def ensure_community_tables():
    """Create community tables on an existing database (migration)."""
    conn = get_connection(DB_PATH)
    conn.executescript(COMMUNITY_TABLES)
    conn.close()


if __name__ == "__main__":
    init_db()
