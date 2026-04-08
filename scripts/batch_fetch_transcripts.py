#!/usr/bin/env python3
"""Batch fetch transcripts for selected channels."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import DB_PATH
from backend.services.transcript_analyzer import (
    get_recent_video_id, get_video_title, fetch_transcript, MAX_TRANSCRIPT_CHARS,
)
from shared_lib.db import get_connection, query_db

SELECTED_IDS = [
    169, 651, 115, 127, 566, 136, 682, 159,  # S-tier
    634, 176, 541, 185, 552, 570, 580, 683,  # A-tier
    627, 657, 545, 667, 125,                   # B-tier
    132, 648, 699,                              # C-tier
    725, 711, 732,                              # D-tier
]

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "batch_transcripts.json")


def main():
    conn = get_connection(DB_PATH)
    placeholders = ",".join("?" * len(SELECTED_IDS))
    channels = query_db(conn, f"""
        SELECT id, name, url, primary_category, tier, composite_score, language
        FROM channels WHERE id IN ({placeholders})
    """, SELECTED_IDS)
    conn.close()

    # Index by id
    ch_map = {ch["id"]: dict(ch) for ch in channels}

    results = []
    for cid in SELECTED_IDS:
        ch = ch_map.get(cid)
        if not ch:
            print(f"  SKIP #{cid}: not found")
            continue

        print(f"[{ch['tier']}] #{cid} {ch['name'][:40]:40s} ... ", end="", flush=True)

        video_id = get_recent_video_id(ch["url"])
        if not video_id:
            print("NO VIDEO")
            results.append({"id": cid, "name": ch["name"], "status": "no_video"})
            continue

        transcript = fetch_transcript(video_id)
        if not transcript:
            print(f"NO TRANSCRIPT (vid={video_id})")
            results.append({"id": cid, "name": ch["name"], "video_id": video_id, "status": "no_transcript"})
            continue

        title = get_video_title(video_id)
        truncated = transcript[:MAX_TRANSCRIPT_CHARS]

        print(f"OK ({len(transcript)} chars, vid={video_id})")
        results.append({
            "id": cid,
            "name": ch["name"],
            "tier": ch["tier"],
            "category": ch["primary_category"],
            "video_id": video_id,
            "video_title": title,
            "transcript": truncated,
            "transcript_length": len(transcript),
            "status": "ok",
        })

    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"\nDone: {ok_count}/{len(SELECTED_IDS)} transcripts fetched")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    main()
