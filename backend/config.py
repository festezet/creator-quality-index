"""Configuration for creator-quality-index."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "benchmark.db")
LOG_DIR = os.path.join(DATA_DIR, "logs")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
DOCS_DIR = os.path.join(PROJECT_DIR, "docs")

# Database mode: PostgreSQL if DATABASE_URL set, else SQLite
DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = DATABASE_URL is not None

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5065))
DEBUG = not IS_POSTGRES
SERVICE_NAME = "creator-quality-index"

# Scoring weights (manual/editorial — 5 criteria incl. Production)
WEIGHTS = {
    "research_depth": 0.25,
    "production": 0.20,
    "signal_noise": 0.25,
    "originality": 0.15,
    "lasting_impact": 0.15,
}

# AI scoring weights (4 criteria — Production excluded, not evaluable from
# a text transcript). Reweighted to sum to 1.0. Production is surfaced as a
# separate editorial badge, not folded into the AI composite.
WEIGHTS_AI = {
    "research_depth": 0.30,
    "signal_noise": 0.30,
    "originality": 0.20,
    "lasting_impact": 0.20,
}

# Tier thresholds (shared by manual and AI composites)
TIERS = {
    "S": 8.5,
    "A": 7.0,
    "B": 5.5,
    "C": 4.0,
}

# AI score validity thresholds (number of scored videos per channel)
AI_SCORE_CONFIRMED_MIN = 20   # >= 20 videos -> 'confirmed'
AI_SCORE_PROVISIONAL_MIN = 10  # 10-19 videos -> 'provisional'; < 10 -> no score
