"""Stats routes for YouTube Creator Quality Index API."""
from flask import Blueprint

try:
    from shared_lib.flask_helpers import success
except ImportError:
    from backend.helpers import success

from backend.db_adapter import db_query

stats_bp = Blueprint("stats", __name__)


@stats_bp.route("/api/stats", methods=["GET"])
def get_stats():
    """Aggregated benchmark stats."""
    total = db_query("SELECT COUNT(*) as count FROM channels WHERE is_reviewed = 1", one=True)["count"]

    tier_dist = db_query(
        "SELECT tier, COUNT(*) as count FROM channels WHERE is_reviewed = 1 AND tier IS NOT NULL GROUP BY tier ORDER BY tier")

    cat_dist = db_query(
        "SELECT primary_category as category, COUNT(*) as count FROM channels WHERE is_reviewed = 1 GROUP BY primary_category ORDER BY count DESC")

    avg_row = db_query("""
        SELECT
          ROUND(AVG(composite_score), 2) as avg_score,
          ROUND(AVG(score_research_depth), 2) as avg_research,
          ROUND(AVG(score_production), 2) as avg_production,
          ROUND(AVG(score_signal_noise), 2) as avg_signal_noise,
          ROUND(AVG(score_originality), 2) as avg_originality,
          ROUND(AVG(score_lasting_impact), 2) as avg_impact
        FROM channels WHERE is_reviewed = 1 AND composite_score IS NOT NULL""", one=True)

    lang_dist = db_query(
        "SELECT language, COUNT(*) as count FROM channels WHERE is_reviewed = 1 GROUP BY language ORDER BY count DESC")

    return success({
        "total_channels": total,
        "tier_distribution": tier_dist,
        "category_distribution": cat_dist,
        "language_distribution": lang_dist,
        "averages": avg_row or {},
    })
