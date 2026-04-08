"""YouTube Creator Quality Index — Flask application."""
import sys
import os
import mimetypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, make_response

mimetypes.add_type("image/webp", ".webp")

# Use shared_lib locally, fallback to inline helpers on Render
try:
    from shared_lib.flask_helpers import setup_cors, register_health, success
    from shared_lib.logging import setup_logger
except ImportError:
    from backend.helpers import setup_cors, register_health, success, setup_logger

from backend.config import HOST, PORT, DEBUG, SERVICE_NAME, FRONTEND_DIR, DOCS_DIR, DB_PATH, IS_POSTGRES

logger = setup_logger(SERVICE_NAME)

app = Flask(__name__, static_folder=None)
setup_cors(app)
register_health(app, SERVICE_NAME)

# Register blueprints
from backend.routes.channels import channels_bp
from backend.routes.categories import categories_bp
from backend.routes.stats import stats_bp
from backend.routes.community import community_bp

app.register_blueprint(channels_bp)
app.register_blueprint(categories_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(community_bp)



@app.route("/")
def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return jsonify({"error": "index.html not found", "path": index_path}), 404
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@app.route("/google34d892dfcaaecc3b.html")
def google_verification():
    resp = make_response("google-site-verification: google34d892dfcaaecc3b.html")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@app.route("/robots.txt")
def robots_txt():
    content = """User-agent: *
Allow: /
Sitemap: https://creator-quality-index.onrender.com/sitemap.xml
"""
    resp = make_response(content)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@app.route("/sitemap.xml")
def sitemap_xml():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://creator-quality-index.onrender.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://creator-quality-index.onrender.com/#methodology</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
"""
    resp = make_response(content)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    return resp


@app.route("/static/<path:filename>")
def serve_static(filename):
    file_path = os.path.join(FRONTEND_DIR, "static", filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    mode = "r" if mime_type.startswith("text/") or mime_type in ("application/javascript", "application/json") else "rb"
    with open(file_path, mode, **{"encoding": "utf-8"} if mode == "r" else {}) as f:
        data = f.read()
    resp = make_response(data)
    resp.headers["Content-Type"] = mime_type
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.route("/api/methodology", methods=["GET"])
def get_methodology():
    """Serve methodology document as markdown."""
    md_path = os.path.join(DOCS_DIR, "METHODOLOGY.md")
    if not os.path.exists(md_path):
        return success({"content": "Methodology document not yet available."})
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    return success({"content": content})


# Initialize database on startup
if IS_POSTGRES:
    from backend.init_pg import init_pg
    init_pg()
elif not os.path.exists(DB_PATH):
    from backend.init_db import init_db
    init_db()
else:
    # Ensure community tables exist on existing SQLite databases
    from backend.init_db import ensure_community_tables
    ensure_community_tables()

if __name__ == "__main__":
    logger.info(f"Starting {SERVICE_NAME} on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)
