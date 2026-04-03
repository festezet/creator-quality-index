"""Populate benchmark.db with the most-watched YouTube channels worldwide,
scored against our 5 intellectual quality criteria.

This creates the core contrast of the index: popularity ≠ quality.
Channels are scored honestly — high production value is acknowledged,
but clickbait, filler, and lack of depth are penalized.

Subscriber counts as of March 2026.
"""
import sqlite3
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "benchmark.db",
)

WEIGHTS = {
    "research_depth": 0.25,
    "production": 0.20,
    "signal_noise": 0.25,
    "originality": 0.15,
    "lasting_impact": 0.15,
}
TIERS = {"S": 8.5, "A": 7.0, "B": 5.5, "C": 4.0}


def compute_score(rd, pr, sn, ori, li):
    return rd * 0.25 + pr * 0.20 + sn * 0.25 + ori * 0.15 + li * 0.15


def compute_tier(score):
    for tier, threshold in TIERS.items():
        if score >= threshold:
            return tier
    return "D"


# New categories for mainstream content
NEW_CATEGORIES = [
    ("entertainment", "Entertainment", "🎭", 13),
    ("music", "Music", "🎵", 14),
    ("kids-family", "Kids & Family", "👶", 15),
    ("sports-media", "Sports & Media", "📺", 16),
    ("gaming", "Gaming", "🎮", 17),
    ("lifestyle", "Lifestyle", "✨", 18),
]

# (name, url, category, lang, subs_millions,
#  research_depth, production, signal_noise, originality, lasting_impact,
#  description)
POPULAR_CHANNELS = [
    # === ENTERTAINMENT ===
    ("MrBeast", "https://youtube.com/@MrBeast", "entertainment", "en", 474,
     3, 9, 3, 6, 3,
     "Elaborate challenges, giveaways, and stunts. Highest production value on YouTube but optimized for engagement over substance."),
    ("PewDiePie", "https://youtube.com/@PewDiePie", "entertainment", "en", 110,
     2, 5, 3, 5, 3,
     "Gaming commentary and reactions. Pioneered the modern YouTuber format but content is largely ephemeral."),
    ("Stokes Twins", "https://youtube.com/@StokesTwins", "entertainment", "en", 138,
     1, 6, 2, 3, 1,
     "Prank and challenge content. High energy, zero substance."),
    ("Dude Perfect", "https://youtube.com/@DudePerfect", "entertainment", "en", 60,
     2, 8, 4, 5, 2,
     "Trick shots and sports entertainment. Impressive production but repetitive formula."),
    ("5-Minute Crafts", "https://youtube.com/@5MinuteCrafts", "entertainment", "en", 81,
     1, 4, 1, 2, 1,
     "DIY hacks, many debunked as fake or dangerous. The epitome of engagement-farming content."),
    ("Logan Paul", "https://youtube.com/@LoganPaul", "entertainment", "en", 24,
     1, 6, 2, 3, 1,
     "Vlogs, boxing, and controversy-driven content."),
    ("KSI", "https://youtube.com/@KSI", "entertainment", "en", 24,
     1, 6, 2, 3, 1,
     "Entertainment, music, and boxing. Built on personality rather than content quality."),
    ("A4", "https://youtube.com/@A4", "entertainment", "ru", 93,
     1, 6, 2, 3, 1,
     "Russian entertainment and challenge videos."),
    ("Alejo Igoa", "https://youtube.com/@AlejoIgoa", "entertainment", "es", 111,
     1, 5, 2, 3, 1,
     "Spanish-language entertainment and comedy."),
    ("Fede Vigevani", "https://youtube.com/@FedeVigevani", "entertainment", "es", 73,
     1, 5, 2, 3, 1,
     "Spanish-language entertainment content."),
    ("ISSEI / いっせい", "https://youtube.com/@issei0806", "entertainment", "ja", 74,
     2, 5, 3, 4, 2,
     "Japanese comedy shorts and skits."),
    ("Zhong", "https://youtube.com/@Zhong", "entertainment", "en", 69,
     1, 5, 2, 3, 1,
     "Short-form comedy and prank content."),
    ("Jimmy Donaldson (MrBeast Gaming)", "https://youtube.com/@MrBeastGaming", "entertainment", "en", 46,
     2, 7, 3, 4, 2,
     "Gaming challenges with MrBeast's production formula."),
    ("Topper Guild", "https://youtube.com/@TopperGuild", "entertainment", "en", 86,
     1, 4, 2, 2, 1,
     "Quick facts and shorts. Rapid-fire format, minimal depth."),

    # === MUSIC ===
    ("T-Series", "https://youtube.com/@tsaborar", "music", "hi", 311,
     2, 6, 4, 3, 4,
     "India's largest music label. Professional production but a corporate catalog, not creator content."),
    ("Zee Music Company", "https://youtube.com/@ZeeMusicCompany", "music", "hi", 122,
     2, 6, 4, 3, 3,
     "Bollywood music label. Corporate music distribution channel."),
    ("BLACKPINK", "https://youtube.com/@BLACKPINK", "music", "ko", 100,
     3, 9, 5, 5, 5,
     "K-Pop group. World-class production but content is promotional, not educational."),
    ("HYBE LABELS", "https://youtube.com/@HYBELABELS", "music", "ko", 81,
     2, 8, 4, 4, 4,
     "K-Pop label (BTS, etc.). Premium music videos and behind-the-scenes."),
    ("Justin Bieber", "https://youtube.com/@JustinBieber", "music", "en", 77,
     2, 8, 4, 4, 4,
     "Pop music. High production music videos."),
    ("BANGTANTV", "https://youtube.com/@BANGTANTV", "music", "ko", 83,
     2, 7, 4, 4, 4,
     "BTS official channel. Fan content and music."),
    ("Canal KondZilla", "https://youtube.com/@CanalKondZilla", "music", "pt", 68,
     2, 7, 3, 4, 3,
     "Brazilian funk music videos. High production value for the genre."),
    ("YRF", "https://youtube.com/@YRF", "music", "hi", 72,
     2, 7, 4, 3, 4,
     "Yash Raj Films music. Bollywood soundtrack distribution."),

    # === KIDS & FAMILY ===
    ("Cocomelon", "https://youtube.com/@Cocomelon", "kids-family", "en", 200,
     3, 7, 5, 4, 4,
     "Nursery rhymes and children's songs. Polished 3D animation, educational for toddlers but formulaic."),
    ("Vlad and Niki", "https://youtube.com/@VladandNiki", "kids-family", "en", 149,
     1, 5, 2, 2, 1,
     "Children playing with toys. Algorithmically optimized, minimal educational value."),
    ("Kids Diana Show", "https://youtube.com/@KidsDianaShow", "kids-family", "en", 138,
     1, 5, 2, 2, 1,
     "Children's play content. Similar format to dozens of other kids channels."),
    ("Like Nastya", "https://youtube.com/@LikeNastya", "kids-family", "en", 132,
     1, 5, 2, 2, 1,
     "Children's entertainment. Formulaic algorithm-friendly content."),
    ("ChuChu TV", "https://youtube.com/@ChuChuTV", "kids-family", "en", 98,
     3, 6, 4, 3, 3,
     "Nursery rhymes and educational songs. Some genuine educational intent."),
    ("Baby Shark - Pinkfong", "https://youtube.com/@Pinkfong", "kids-family", "en", 84,
     2, 6, 3, 3, 2,
     "Children's music. One viral hit, rest is formulaic follow-ups."),
    ("Toys and Colors", "https://youtube.com/@ToysAndColors", "kids-family", "en", 82,
     1, 4, 2, 2, 1,
     "Children playing with toys. Pure algorithm fodder."),
    ("El Reino Infantil", "https://youtube.com/@ElReinoInfantil", "kids-family", "es", 71,
     2, 5, 3, 3, 2,
     "Spanish children's songs and nursery rhymes."),
    ("Infobells - Hindi", "https://youtube.com/@InfobellsHindi", "kids-family", "hi", 72,
     3, 5, 4, 3, 3,
     "Hindi educational content for children. Some genuine learning value."),

    # === SPORTS & MEDIA (TV networks, sports, news) ===
    ("SET India", "https://youtube.com/@SETIndia", "sports-media", "hi", 189,
     2, 5, 3, 2, 2,
     "Sony Entertainment Television India. TV show clips uploaded to YouTube."),
    ("Sony SAB", "https://youtube.com/@SonySAB", "sports-media", "hi", 105,
     2, 5, 3, 2, 2,
     "Indian TV comedy channel. Sitcom clips."),
    ("WWE", "https://youtube.com/@WWE", "sports-media", "en", 112,
     2, 7, 3, 3, 3,
     "Professional wrestling clips. High production but scripted entertainment."),
    ("UR · Cristiano", "https://youtube.com/@Cristiano", "sports-media", "en", 79,
     1, 5, 3, 2, 2,
     "Cristiano Ronaldo's personal channel. Celebrity content."),
    ("Zee TV", "https://youtube.com/@ZeeTV", "sports-media", "hi", 98,
     2, 5, 3, 2, 2,
     "Indian TV network clips on YouTube."),
    ("Colors TV", "https://youtube.com/@ColorsTV", "sports-media", "hi", 82,
     2, 5, 3, 2, 2,
     "Indian TV entertainment clips."),
    ("Aaj Tak", "https://youtube.com/@AajTak", "sports-media", "hi", 75,
     4, 5, 3, 2, 3,
     "Indian Hindi news channel. Journalism with sensationalist tendencies."),
    ("HAR PAL GEO", "https://youtube.com/@HARPALGEO", "sports-media", "ur", 72,
     2, 5, 3, 2, 2,
     "Pakistani TV drama and entertainment clips."),

    # === GAMING ===
    ("김프로KIMPRO", "https://youtube.com/@kimpro", "gaming", "ko", 131,
     2, 6, 3, 4, 2,
     "Korean comedy and gaming content."),

    # === LIFESTYLE ===
    ("Bispo Bruno Leonardo", "https://youtube.com/@BispoBrunoLeonardo", "lifestyle", "pt", 72,
     2, 4, 3, 2, 2,
     "Brazilian religious content and motivational speaking."),

    # === Channels already popular but with ACTUAL quality (for contrast) ===
    # Mark Rober already in our DB, but let's add some that bridge the gap
    ("Veritasium (Popular)", "https://youtube.com/@veritasium", "science", "en", 18,
     9, 9, 8, 8, 9,
     "Already in index. 18M subs proves quality can reach mass audiences."),
    # Skip - already exists

    # === Additional high-sub entertainment for contrast ===
    ("Alan's Universe", "https://youtube.com/@AlansUniverse", "kids-family", "es", 100,
     1, 4, 2, 2, 1,
     "Spanish children's content."),
    ("YOLO AVENTURAS", "https://youtube.com/@YOLOAventuras", "entertainment", "es", 68,
     1, 5, 2, 3, 1,
     "Spanish-language adventure and challenge content."),
    ("KL BRO Biju Rithvik", "https://youtube.com/@KLBROBijuRithvik", "entertainment", "ml", 83,
     1, 4, 2, 2, 1,
     "Malayalam entertainment and comedy."),
    ("ZAMZAM BROTHERS", "https://youtube.com/@ZAMZAMBrothers", "entertainment", "ar", 82,
     1, 4, 2, 2, 1,
     "Arabic entertainment content."),
    ("Anaya Kandhal", "https://youtube.com/@AnayaKandhal", "entertainment", "hi", 70,
     1, 4, 2, 2, 1,
     "Indian entertainment and shorts."),
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Add new categories
    for slug, name, icon, sort_order in NEW_CATEGORIES:
        cur.execute(
            "INSERT OR IGNORE INTO categories (slug, name, icon, sort_order) VALUES (?, ?, ?, ?)",
            (slug, name, icon, sort_order),
        )
    conn.commit()
    print(f"Categories added/verified: {len(NEW_CATEGORIES)}")

    # 2. Get existing channels for dedup
    existing = set()
    for row in cur.execute("SELECT name, url FROM channels"):
        existing.add(row[0].lower())
        existing.add(row[1].lower())

    inserted = 0
    skipped = 0

    for ch in POPULAR_CHANNELS:
        name, url, cat, lang, subs_m, rd, pr, sn, ori, li, desc = ch

        if name.lower() in existing or url.lower() in existing:
            skipped += 1
            continue

        score = compute_score(rd, pr, sn, ori, li)
        tier = compute_tier(score)
        subs = subs_m * 1_000_000

        cur.execute("""
            INSERT INTO channels (
                name, url, platform, language, primary_category,
                description, subscriber_count,
                score_research_depth, score_production,
                score_signal_noise, score_originality, score_lasting_impact,
                composite_score, tier, is_reviewed
            ) VALUES (?, ?, 'youtube', ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            name, url, lang, cat, desc, subs,
            rd, pr, sn, ori, li,
            round(score, 2), tier,
        ))
        existing.add(name.lower())
        existing.add(url.lower())
        inserted += 1

        print(f"  + {tier} ({score:.1f}) {name} [{cat}] — {subs_m}M subs")

    conn.commit()

    # 3. Summary
    print(f"\n{'='*60}")
    print(f"Inserted: {inserted} | Skipped (dupes): {skipped}")

    # Category breakdown
    print("\nChannels per category:")
    for row in cur.execute("""
        SELECT cat.name, COUNT(*) as cnt
        FROM channels c
        JOIN categories cat ON c.primary_category = cat.slug
        GROUP BY cat.name
        ORDER BY cat.sort_order
    """):
        print(f"   {row[1]:>3}  {row[0]}")

    total = cur.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    print(f"\nTotal channels: {total}")

    # Popularity vs Quality contrast
    print("\n" + "="*60)
    print("POPULARITY vs QUALITY CONTRAST")
    print("="*60)
    for row in cur.execute("""
        SELECT name, subscriber_count, composite_score, tier, primary_category
        FROM channels
        WHERE subscriber_count IS NOT NULL
        ORDER BY subscriber_count DESC
        LIMIT 20
    """):
        subs = row[1] // 1_000_000
        print(f"  {subs:>4}M subs | {row[3]} ({row[2]:.1f}) | {row[0]}")

    conn.close()


if __name__ == "__main__":
    main()
