"""Channel routes for YouTube Creator Quality Index API."""
import json

from flask import Blueprint, request

try:
    from shared_lib.flask_helpers import success, error
except ImportError:
    from backend.helpers import success, error

from backend.db_adapter import db_query

channels_bp = Blueprint("channels", __name__)


@channels_bp.route("/api/channels", methods=["GET"])
def list_channels():
    """List channels with filtering, sorting, pagination."""
    category = request.args.get("category")
    tier = request.args.get("tier")
    lang = request.args.get("lang")
    search = request.args.get("search")
    sort = request.args.get("sort", "composite_score")
    order = request.args.get("order", "desc")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    allowed_sorts = {
        "composite_score", "name", "subscriber_count",
        "score_research_depth", "score_production",
        "score_signal_noise", "score_originality",
        "score_lasting_impact", "created_at",
        "ai_score_research", "ai_score_signal_noise",
        "ai_score_originality", "ai_score_lasting_impact",
    }
    if sort not in allowed_sorts:
        sort = "composite_score"
    if order not in ("asc", "desc"):
        order = "desc"

    where = ["c.is_reviewed = TRUE"]
    params = []

    if category:
        where.append("c.primary_category = ?")
        params.append(category)
    if tier:
        where.append("c.tier = ?")
        params.append(tier.upper())
    if lang:
        where.append("c.language = ?")
        params.append(lang)
    if search:
        where.append("(c.name LIKE ? OR c.description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where_clause = " AND ".join(where)

    total = db_query(f"SELECT COUNT(*) as total FROM channels c WHERE {where_clause}", params, one=True)["total"]

    null_sort = f"CASE WHEN {sort} IS NULL THEN 1 ELSE 0 END, "
    sql = f"""
        SELECT c.*, cat.name as category_name, cat.icon as category_icon
        FROM channels c
        LEFT JOIN categories cat ON c.primary_category = cat.slug
        WHERE {where_clause}
        ORDER BY {null_sort}{sort} {order}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = db_query(sql, params)

    channels = []
    for ch in rows:
        if ch.get("sample_videos"):
            try:
                ch["sample_videos"] = json.loads(ch["sample_videos"])
            except (json.JSONDecodeError, TypeError):
                ch["sample_videos"] = []
        else:
            ch["sample_videos"] = []
        channels.append(ch)

    return success({
        "channels": channels,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@channels_bp.route("/api/channels/<int:channel_id>", methods=["GET"])
def get_channel(channel_id):
    """Get a single channel by ID."""
    sql = """
        SELECT c.*, cat.name as category_name, cat.icon as category_icon
        FROM channels c
        LEFT JOIN categories cat ON c.primary_category = cat.slug
        WHERE c.id = ?
    """
    ch = db_query(sql, [channel_id], one=True)

    if not ch:
        return error("Channel not found", 404)

    if ch.get("sample_videos"):
        try:
            ch["sample_videos"] = json.loads(ch["sample_videos"])
        except (json.JSONDecodeError, TypeError):
            ch["sample_videos"] = []
    else:
        ch["sample_videos"] = []

    return success(ch)
