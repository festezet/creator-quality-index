"""Community routes — voting and comments for YouTube Creator Quality Index."""
import hashlib
import time

from flask import Blueprint, request

try:
    from shared_lib.flask_helpers import success, error
except ImportError:
    from backend.helpers import success, error

from backend.db_adapter import db_query, db_execute
from backend.config import IS_POSTGRES

community_bp = Blueprint("community", __name__)

# Rate limit storage (in-memory, resets on restart — acceptable for free tier)
_rate_limits = {}  # {visitor_id: {"comments": [(timestamp, ...)]}}

COMMENT_LIMIT = 5  # per hour


def _get_visitor_id():
    """Generate a visitor ID from IP + User-Agent."""
    ip = request.remote_addr or "unknown"
    ua = request.headers.get("User-Agent", "")
    raw = f"{ip}:{ua}:cqi-salt-2024"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _check_rate_limit(visitor_id, action):
    """Check and enforce rate limits. Returns True if allowed."""
    now = time.time()
    hour_ago = now - 3600

    if visitor_id not in _rate_limits:
        _rate_limits[visitor_id] = {"comments": []}

    entries = _rate_limits[visitor_id].get(action, [])
    # Prune old entries
    _rate_limits[visitor_id][action] = [t for t in entries if t > hour_ago]
    entries = _rate_limits[visitor_id][action]

    limit = COMMENT_LIMIT
    if len(entries) >= limit:
        return False

    _rate_limits[visitor_id][action].append(now)
    return True


@community_bp.route("/api/channels/<int:channel_id>/comments", methods=["GET"])
def get_comments(channel_id):
    """List comments for a channel."""
    limit = min(int(request.args.get("limit", 20)), 50)
    offset = int(request.args.get("offset", 0))

    rows = db_query("""
        SELECT id, visitor_name, content, upvotes, created_at, parent_id
        FROM comments
        WHERE channel_id = ? AND is_visible = 1
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [channel_id, limit, offset])

    total = db_query(
        "SELECT COUNT(*) as count FROM comments WHERE channel_id = ? AND is_visible = 1",
        [channel_id], one=True
    )["count"]

    return success({"comments": rows, "total": total})


@community_bp.route("/api/channels/<int:channel_id>/comments", methods=["POST"])
def post_comment(channel_id):
    """Post a comment on a channel."""
    visitor_id = _get_visitor_id()

    if not _check_rate_limit(visitor_id, "comments"):
        return error("Rate limit exceeded (max 5 comments/hour)", 429)

    data = request.get_json()
    if not data or not data.get("content"):
        return error("Missing 'content' field", 400)

    content = data["content"].strip()
    if len(content) < 1 or len(content) > 2000:
        return error("Content must be between 1 and 2000 characters", 400)

    visitor_name = (data.get("name") or "Anonymous").strip()[:50]
    parent_id = data.get("parent_id")

    # Validate channel exists
    ch = db_query("SELECT id FROM channels WHERE id = ?", [channel_id], one=True)
    if not ch:
        return error("Channel not found", 404)

    # Validate parent comment if provided
    if parent_id:
        parent = db_query("SELECT id FROM comments WHERE id = ? AND channel_id = ?", [parent_id, channel_id], one=True)
        if not parent:
            return error("Parent comment not found", 404)

    if IS_POSTGRES:
        sql = ("INSERT INTO comments (channel_id, visitor_id, visitor_name, content, parent_id) "
               "VALUES (?, ?, ?, ?, ?) RETURNING id")
    else:
        sql = ("INSERT INTO comments (channel_id, visitor_id, visitor_name, content, parent_id) "
               "VALUES (?, ?, ?, ?, ?)")

    comment_id = db_execute(sql, [channel_id, visitor_id, visitor_name, content, parent_id])

    return success({"id": comment_id, "message": "Comment posted"}, status_code=201)


@community_bp.route("/api/comments/<int:comment_id>/upvote", methods=["POST"])
def upvote_comment(comment_id):
    """Upvote a comment."""
    visitor_id = _get_visitor_id()

    comment = db_query("SELECT id, upvotes FROM comments WHERE id = ?", [comment_id], one=True)
    if not comment:
        return error("Comment not found", 404)

    db_execute("UPDATE comments SET upvotes = upvotes + 1 WHERE id = ?", [comment_id])

    return success({"upvotes": comment["upvotes"] + 1})
