"""YouTube Creator Quality Index — Flask application."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory, jsonify

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
    try:
        return send_from_directory(FRONTEND_DIR, "index.html")
    except Exception as e:
        return jsonify({"error": str(e), "frontend_dir": FRONTEND_DIR,
                        "exists": os.path.exists(FRONTEND_DIR),
                        "index_exists": os.path.exists(os.path.join(FRONTEND_DIR, "index.html"))}), 500


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, "static"), filename)


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
