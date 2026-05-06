"""Flask-Limiter setup — IP-level rate limiting (defense-in-depth).

In-memory storage (resets on restart) is acceptable for free tier with a single
worker. Scaling to multiple workers requires a shared backend (Redis).

The limiter only complements existing per-visitor logic in community.py: this
layer cuts dumb scrapers and bots before the request even reaches the route.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# Conservative default: any unspecified endpoint gets 200/hour per IP.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour"],
    storage_uri="memory://",
    headers_enabled=True,  # add X-RateLimit-* response headers
    strategy="fixed-window",
)
