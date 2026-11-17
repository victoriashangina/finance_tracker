#!/bin/sh
set -eu
python -m pip install -r requirements.lock.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
