#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec waitress-serve --listen=0.0.0.0:8000 config.wsgi:application
