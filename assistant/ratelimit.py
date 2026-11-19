"""
Fixed-window request limits per user, kept in the shared cache so they hold
across worker processes. They cap what a single account can cost and
blunt scripted abuse; they aren't meant to be exact to the request.
"""

import time

from django.conf import settings
from django.core.cache import cache


def allow_request(user_id):
    """Count one request for `user_id`; False if any window's limit is exceeded."""
    now = int(time.time())
    windows = [
        (60, settings.ASSISTANT_REQUESTS_PER_MINUTE),
        (86_400, settings.ASSISTANT_REQUESTS_PER_DAY),
    ]
    allowed = True
    for seconds, limit in windows:
        key = f"assistant:{user_id}:{seconds}:{now // seconds}"
        cache.add(key, 0, timeout=seconds)
        try:
            count = cache.incr(key)
        except ValueError:  # expired between add() and incr()
            cache.set(key, 1, timeout=seconds)
            count = 1
        if count > limit:
            allowed = False
    return allowed
