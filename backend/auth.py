"""HTTP Basic Auth for admin routes.

Reads ADMIN_PASSWORD from environment. If unset, all admin endpoints return 503
(safer than serving them unauthenticated in production).

Username is fixed to "admin"; only the password is a secret.
"""
import os
from functools import wraps

from flask import request, Response


ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
REALM = 'Basic realm="CQI Admin", charset="UTF-8"'


def _unauthorized():
    return Response(
        "Authentication required.",
        status=401,
        headers={"WWW-Authenticate": REALM},
    )


def _misconfigured():
    return Response(
        "Admin authentication not configured (ADMIN_PASSWORD env var missing).",
        status=503,
    )


def require_admin_auth(view):
    """Decorator that gates a route behind HTTP Basic Auth."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not ADMIN_PASSWORD:
            return _misconfigured()
        auth = request.authorization
        if (
            not auth
            or auth.username != ADMIN_USERNAME
            or auth.password != ADMIN_PASSWORD
        ):
            return _unauthorized()
        return view(*args, **kwargs)
    return wrapper
