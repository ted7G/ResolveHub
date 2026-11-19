#!/usr/bin/env bash
# Render build step. Runs on every deploy; every command is safe to repeat.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createcachetable
python manage.py setup_roles
