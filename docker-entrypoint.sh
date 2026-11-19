#!/bin/sh
# Brings the database up to date, then starts the given command (the web
# server by default). Every step is safe to repeat on each deploy.
set -e

python manage.py migrate --no-input
python manage.py createcachetable
python manage.py setup_roles

exec "$@"
