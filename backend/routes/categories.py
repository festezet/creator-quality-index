"""Category routes for YouTube Creator Quality Index API."""
from flask import Blueprint

try:
    from shared_lib.flask_helpers import success
except ImportError:
    from backend.helpers import success

from backend.db_adapter import db_query

categories_bp = Blueprint("categories", __name__)


@categories_bp.route("/api/categories", methods=["GET"])
def list_categories():
    """List categories with channel counts."""
    sql = """
        SELECT cat.slug, cat.name, cat.icon, cat.sort_order,
               COUNT(ch.id) as channel_count
        FROM categories cat
        LEFT JOIN channels ch ON ch.primary_category = cat.slug AND ch.is_reviewed = 1
        GROUP BY cat.slug, cat.name, cat.icon, cat.sort_order
        ORDER BY cat.sort_order
    """
    rows = db_query(sql)
    return success(rows)
