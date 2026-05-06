"""Admin routes — synthesis table and scraping status."""
import json
import os

from flask import Blueprint, request

try:
    from shared_lib.flask_helpers import success, error
except ImportError:
    from backend.helpers import success, error

from backend.db_adapter import db_query
from backend.auth import require_admin_auth

admin_bp = Blueprint("admin", __name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def _load_transcript_map():
    """Load transcript status from all_transcripts.json and local_transcripts.json."""
    transcript_map = {}

    # Main transcripts file
    all_path = os.path.join(DATA_DIR, "all_transcripts.json")
    if os.path.exists(all_path):
        with open(all_path, "r", encoding="utf-8") as f:
            for t in json.load(f):
                cid = t.get("id")
                if cid is not None:
                    transcript_map[cid] = {
                        "status": t.get("status", "unknown"),
                        "source": t.get("source", "unknown"),
                        "length": t.get("transcript_length", 0),
                        "video_id": t.get("video_id"),
                        "video_title": t.get("video_title"),
                    }

    # Local fetch results (override if newer/different)
    local_path = os.path.join(DATA_DIR, "local_transcripts.json")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            for t in json.load(f):
                cid = t.get("id")
                if cid is not None and cid not in transcript_map:
                    transcript_map[cid] = {
                        "status": t.get("status", "unknown"),
                        "source": "local_fetch",
                        "length": t.get("transcript_length", 0),
                        "video_id": t.get("video_id"),
                        "video_title": t.get("video_title"),
                    }

    return transcript_map


def _load_score_files_map():
    """Load AI score file status from data/ai_scores/."""
    scores_dir = os.path.join(DATA_DIR, "ai_scores")
    score_map = {}
    if not os.path.isdir(scores_dir):
        return score_map

    for fname in os.listdir(scores_dir):
        if not fname.startswith("scores_") or not fname.endswith(".json"):
            continue
        try:
            cid = int(fname.replace("scores_", "").replace(".json", ""))
        except ValueError:
            continue
        fpath = os.path.join(scores_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("status") == "skipped":
                score_map[cid] = "skipped"
            elif "research_depth" in data:
                score_map[cid] = "scored"
            elif "scores" in data and "research_depth" in data.get("scores", {}):
                score_map[cid] = "scored"
            else:
                score_map[cid] = "unknown_format"
        except (json.JSONDecodeError, OSError):
            score_map[cid] = "error"

    return score_map


def _load_video_scores_map():
    """Load per-channel video scoring counts from video_scores table."""
    try:
        rows = db_query("""
            SELECT channel_id, COUNT(*) as scored
            FROM video_scores
            GROUP BY channel_id
        """)
        return {r["channel_id"]: r["scored"] for r in rows}
    except Exception:
        return {}


@admin_bp.route("/api/admin/synthesis", methods=["GET"])
@require_admin_auth
def synthesis():
    """Return synthesis table: all channels with transcript + AI score status."""
    channels = db_query("""
        SELECT id, name, tier, primary_category, language,
               composite_score,
               score_research_depth, score_production, score_signal_noise,
               score_originality, score_lasting_impact,
               ai_score_research, ai_score_signal_noise,
               ai_score_originality, ai_score_lasting_impact,
               ai_analysis_date, ai_videos_scored, ai_videos_target
        FROM channels
        ORDER BY id
    """)

    transcript_map = _load_transcript_map()
    score_file_map = _load_score_files_map()
    video_scores_map = _load_video_scores_map()

    results = []
    stats = {
        "total": len(channels),
        "with_transcript": 0,
        "transcript_ok": 0,
        "with_ai_score": 0,
        "no_transcript": 0,
        "by_transcript_status": {},
        "by_tier": {},
        "total_videos_scored": 0,
        "video_coverage": {"complete": 0, "partial": 0, "none": 0},
    }

    for ch in channels:
        cid = ch["id"]
        t_info = transcript_map.get(cid, {})
        t_status = t_info.get("status", "no_entry")
        score_file_status = score_file_map.get(cid, "no_file")
        has_ai = ch.get("ai_score_research") is not None
        videos_scored = video_scores_map.get(cid, 0)
        videos_target = ch.get("ai_videos_target") or 26

        if t_status != "no_entry":
            stats["with_transcript"] += 1
        if t_status == "ok":
            stats["transcript_ok"] += 1
        if has_ai:
            stats["with_ai_score"] += 1
        if t_status == "no_entry":
            stats["no_transcript"] += 1

        # Video coverage stats
        stats["total_videos_scored"] += videos_scored
        if videos_scored >= videos_target:
            stats["video_coverage"]["complete"] += 1
        elif videos_scored > 0:
            stats["video_coverage"]["partial"] += 1
        else:
            stats["video_coverage"]["none"] += 1

        # Count by transcript status
        stats["by_transcript_status"][t_status] = stats["by_transcript_status"].get(t_status, 0) + 1

        # Count by tier
        tier = ch.get("tier", "?")
        if tier not in stats["by_tier"]:
            stats["by_tier"][tier] = {"total": 0, "ai_scored": 0, "transcript_ok": 0}
        stats["by_tier"][tier]["total"] += 1
        if has_ai:
            stats["by_tier"][tier]["ai_scored"] += 1
        if t_status == "ok":
            stats["by_tier"][tier]["transcript_ok"] += 1

        # Pipeline steps: 1=transcript ok, 2=score file, 3=ai in DB
        pipeline = 0
        if t_status == "ok":
            pipeline += 1
        if score_file_status == "scored":
            pipeline += 1
        if has_ai:
            pipeline += 1

        results.append({
            "id": cid,
            "name": ch["name"],
            "tier": ch.get("tier"),
            "category": ch.get("primary_category"),
            "language": ch.get("language"),
            "composite": ch.get("composite_score"),
            "manual_scores": {
                "R": ch.get("score_research_depth"),
                "P": ch.get("score_production"),
                "S": ch.get("score_signal_noise"),
                "O": ch.get("score_originality"),
                "I": ch.get("score_lasting_impact"),
            },
            "ai_scores": {
                "R": ch.get("ai_score_research"),
                "S": ch.get("ai_score_signal_noise"),
                "O": ch.get("ai_score_originality"),
                "I": ch.get("ai_score_lasting_impact"),
            } if has_ai else None,
            "transcript_status": t_status,
            "transcript_source": t_info.get("source"),
            "transcript_length": t_info.get("length"),
            "video_title": t_info.get("video_title"),
            "score_file": score_file_status,
            "ai_date": ch.get("ai_analysis_date"),
            "pipeline": pipeline,
            "videos_scored": videos_scored,
            "videos_target": videos_target,
        })

    return success({"channels": results, "stats": stats})


# -----------------------------------------------------------------------------
# Pipeline status (Phase A download / Phase B transcribe)
# -----------------------------------------------------------------------------

AUDIO_CACHE_DIR = "/data/fcuda_workspace/youtube/audio_cache"


def _manifest_totals():
    """Count videos per channel in video_manifest.json (capped at 26)."""
    manifest_path = os.path.join(DATA_DIR, "video_manifest.json")
    per_channel = {}
    total = 0
    if not os.path.exists(manifest_path):
        return total, per_channel
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return total, per_channel
    for entry in manifest:
        cid = entry.get("channel_id") or entry.get("id")
        videos = entry.get("video_ids") or entry.get("videos") or []
        n = min(len(videos), 26)
        per_channel[cid] = n
        total += n
    return total, per_channel


def _cache_stats():
    """Return audio cache file count + size in bytes."""
    if not os.path.isdir(AUDIO_CACHE_DIR):
        return {"files": 0, "bytes": 0, "available": False}
    try:
        files = os.listdir(AUDIO_CACHE_DIR)
        n = 0
        size = 0
        for fname in files:
            fpath = os.path.join(AUDIO_CACHE_DIR, fname)
            try:
                size += os.path.getsize(fpath)
                n += 1
            except OSError:
                continue
        return {"files": n, "bytes": size, "available": True}
    except OSError:
        return {"files": 0, "bytes": 0, "available": False}


@admin_bp.route("/api/admin/pipeline", methods=["GET"])
@require_admin_auth
def pipeline_status():
    """Phase A/B pipeline state : status counts, per-channel breakdown, rates, cache.

    Returns {"available": false} when the local-only download_progress table is
    missing (production deployments do not run the audio pipeline).
    """
    # Global status counts — also used to detect missing table
    try:
        status_rows = db_query("""
            SELECT status, COUNT(*) AS n
            FROM download_progress
            GROUP BY status
        """)
    except Exception as exc:
        return success({
            "available": False,
            "reason": "download_progress table not found (pipeline runs locally only)",
            "detail": str(exc).splitlines()[0][:200],
        })
    status_counts = {r["status"]: r["n"] for r in status_rows}

    # Total videos in manifest
    manifest_total, per_channel_total = _manifest_totals()

    # Per-channel stats : transcribed (ok), downloaded waiting, failed
    channel_rows = db_query("""
        SELECT c.id, c.name, c.tier, c.primary_category, c.language,
               SUM(CASE WHEN dp.status = 'ok' THEN 1 ELSE 0 END) AS transcribed,
               SUM(CASE WHEN dp.status = 'downloaded' THEN 1 ELSE 0 END) AS downloaded,
               SUM(CASE WHEN dp.status = 'download_failed' THEN 1 ELSE 0 END) AS dl_failed,
               SUM(CASE WHEN dp.status = 'whisper_failed' THEN 1 ELSE 0 END) AS whisper_failed,
               SUM(CASE WHEN dp.status IN ('rate_limited','timeout','audio_missing') THEN 1 ELSE 0 END) AS retryable,
               COUNT(dp.video_id) AS attempts
        FROM channels c
        LEFT JOIN download_progress dp ON dp.channel_id = c.id
        GROUP BY c.id, c.name, c.tier, c.primary_category, c.language
        ORDER BY transcribed DESC, c.id
    """)
    # Annotate with manifest target
    for row in channel_rows:
        row["target"] = per_channel_total.get(row["id"], 26)
        row["pending"] = max(row["target"] - (row["attempts"] or 0), 0)

    # Recent activity : configurable limit + optional time window
    try:
        recent_limit = max(1, min(int(request.args.get("recent_limit", 200)), 1000))
    except (TypeError, ValueError):
        recent_limit = 200
    try:
        recent_hours = float(request.args.get("recent_hours", 0))
    except (TypeError, ValueError):
        recent_hours = 0
    if recent_hours > 0:
        recent = db_query(f"""
            SELECT video_id, channel_id, status, words, lang, source,
                   last_attempt_at, completed_at, audio_path
            FROM download_progress
            WHERE last_attempt_at IS NOT NULL
              AND last_attempt_at > datetime('now', '-{recent_hours} hours')
            ORDER BY last_attempt_at DESC
            LIMIT {recent_limit}
        """)
    else:
        recent = db_query(f"""
            SELECT video_id, channel_id, status, words, lang, source,
                   last_attempt_at, completed_at, audio_path
            FROM download_progress
            WHERE last_attempt_at IS NOT NULL
            ORDER BY last_attempt_at DESC
            LIMIT {recent_limit}
        """)

    # Rate over last hour : transcribed (ok with completed_at) and downloaded
    rate_ok = db_query("""
        SELECT COUNT(*) AS n FROM download_progress
        WHERE status = 'ok' AND completed_at > datetime('now', '-1 hour')
    """, one=True)
    rate_dl = db_query("""
        SELECT COUNT(*) AS n FROM download_progress
        WHERE last_attempt_at > datetime('now', '-1 hour')
              AND status IN ('downloaded','ok')
    """, one=True)

    # Cache stats
    cache = _cache_stats()

    # ETA estimation
    transcribed_total = status_counts.get("ok", 0)
    remaining = max(manifest_total - transcribed_total, 0)
    rate_ok_h = rate_ok["n"] if rate_ok else 0
    eta_hours = (remaining / rate_ok_h) if rate_ok_h > 0 else None

    return success({
        "status_counts": status_counts,
        "manifest_total": manifest_total,
        "transcribed_total": transcribed_total,
        "remaining": remaining,
        "channels": channel_rows,
        "recent": recent,
        "rates": {
            "transcribed_per_hour": rate_ok_h,
            "downloaded_per_hour": rate_dl["n"] if rate_dl else 0,
        },
        "eta_hours": eta_hours,
        "cache": cache,
    })
