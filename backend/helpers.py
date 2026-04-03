"""Inline helpers for Render deployment (replaces shared_lib dependency).

On Render, shared_lib is not available as a local package.
These helpers provide the same Flask utilities used by the app.
Locally, the app still imports from shared_lib — this module is only
used when shared_lib is unavailable (detected at import time in app.py).
"""
import logging
from functools import wraps

from flask import jsonify, make_response


def success(data=None, status_code=200, **kwargs):
    """Return a success JSON response (matches shared_lib format)."""
    response = {"ok": True}
    if data is not None:
        response["data"] = data
    response.update(kwargs)
    return make_response(jsonify(response), status_code)


def error(message, status_code=400, **kwargs):
    """Return an error JSON response (matches shared_lib format)."""
    response = {"ok": False, "message": str(message)}
    response.update(kwargs)
    return make_response(jsonify(response), status_code)


def setup_cors(app):
    """Enable CORS for all routes."""
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        if response.status_code == 200 and not response.data:
            pass
        return response
    return app


def register_health(app, service_name="app"):
    """Register a /health endpoint."""
    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "service": service_name})


def setup_logger(name, level=logging.INFO):
    """Setup a basic logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
