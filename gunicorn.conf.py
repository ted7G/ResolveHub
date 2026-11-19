"""Gunicorn settings, read automatically when it starts from the project root."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# The AI assistant waits up to ASSISTANT_TIMEOUT_SECONDS for a reply.
timeout = 60
graceful_timeout = 20
accesslog = "-"
