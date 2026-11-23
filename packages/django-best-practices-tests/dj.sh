#!/bin/bash
# Run a command with the dependencies of one Django series, for example:
#   ./dj.sh 6.1 python manage.py sqlmigrate fk_naive 0002
set -e
cd "$(dirname "$0")"
version=$1
shift
tasks_db="django-tasks-db"
[ "$version" = "5.2" ] && tasks_db="django-tasks-db[compat]"
export PG_PORT=${PG_PORT:-55416}
exec uv run --quiet --no-project --python "${PYTHON:-3.13}" \
    --with "django~=$version.0" --with "psycopg[binary]" \
    --with pytest --with pytest-django \
    --with "$tasks_db" --with django-q2 --with djangorestframework \
    "$@"
