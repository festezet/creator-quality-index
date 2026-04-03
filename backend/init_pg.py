"""Initialize PostgreSQL schema for YouTube Creator Quality Index."""
from backend.db_adapter import get_db, release_db

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    channel_id TEXT UNIQUE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    platform TEXT DEFAULT 'youtube',
    language TEXT DEFAULT 'en',
    primary_category TEXT NOT NULL REFERENCES categories(slug),
    description TEXT,

    subscriber_count INTEGER,
    total_views BIGINT,
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
    is_reviewed BOOLEAN DEFAULT FALSE,
    is_featured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_channels_category ON channels(primary_category);
CREATE INDEX IF NOT EXISTS idx_channels_tier ON channels(tier);
CREATE INDEX IF NOT EXISTS idx_channels_composite ON channels(composite_score DESC);

CREATE TABLE IF NOT EXISTS community_ratings (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    visitor_id VARCHAR(64) NOT NULL,
    criterion TEXT NOT NULL,
    score INTEGER CHECK(score BETWEEN 1 AND 10),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(channel_id, visitor_id, criterion)
);

CREATE TABLE IF NOT EXISTS comments (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES comments(id) ON DELETE CASCADE,
    visitor_id VARCHAR(64) NOT NULL,
    visitor_name VARCHAR(50) DEFAULT 'Anonymous',
    content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 2000),
    upvotes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    is_visible BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_ratings_channel ON community_ratings(channel_id);
CREATE INDEX IF NOT EXISTS idx_comments_channel ON comments(channel_id);
"""

CATEGORIES = [
    ("science", "Science", "\\U0001f52c", 1),
    ("tech-dev", "Tech & Development", "\\U0001f4bb", 2),
    ("engineering", "Engineering", "\\u2699\\ufe0f", 3),
    ("finance", "Finance & Economics", "\\U0001f4c8", 4),
    ("history", "History", "\\U0001f4dc", 5),
    ("geopolitics", "Geopolitics", "\\U0001f30d", 6),
    ("productivity", "Productivity", "\\u26a1", 7),
    ("philosophy-essays", "Philosophy & Essays", "\\U0001f4ad", 8),
    ("design-art", "Design & Art", "\\U0001f3a8", 9),
    ("education", "Education", "\\U0001f4da", 10),
    ("environment", "Environment", "\\U0001f331", 11),
    ("making", "Making & DIY", "\\U0001f527", 12),
    ("entertainment", "Entertainment", "\\U0001f3ad", 13),
    ("music", "Music", "\\U0001f3b5", 14),
    ("kids-family", "Kids & Family", "\\U0001f476", 15),
    ("sports-media", "Sports & Media", "\\U0001f4fa", 16),
    ("gaming", "Gaming", "\\U0001f3ae", 17),
    ("lifestyle", "Lifestyle", "\\u2728", 18),
]


def init_pg():
    """Create tables and seed categories in PostgreSQL."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(PG_SCHEMA)
        for slug, name, icon, sort_order in CATEGORIES:
            cur.execute(
                "INSERT INTO categories (slug, name, icon, sort_order) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (slug) DO NOTHING",
                (slug, name, icon, sort_order),
            )
        conn.commit()
        cur.close()
        print("PostgreSQL schema initialized")
    finally:
        release_db(conn)


if __name__ == "__main__":
    init_pg()
