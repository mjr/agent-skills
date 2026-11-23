#!/bin/bash
# Run the rule tests once per Django version against a real PostgreSQL.
#
#   ./run_matrix.sh                   all versions, PostgreSQL 16
#   DJANGO_VERSIONS="6.1" ./run_matrix.sh -k migration
#   PG_PORT=55418 ./run_matrix.sh     PostgreSQL 18 (docker compose up -d pg18)
#
# Extra arguments go to pytest. Each version gets its own throwaway environment
# from uv, so nothing is installed globally.
set -e
cd "$(dirname "$0")"

DJANGO_VERSIONS=${DJANGO_VERSIONS:-"5.2 6.0 6.1"}
PYTHON=${PYTHON:-3.13}
export PG_PORT=${PG_PORT:-55416}

status=0
for version in $DJANGO_VERSIONS; do
    echo "=== Django $version (PostgreSQL on port $PG_PORT)" >&2
    export DBP_DJANGO_SERIES=$version
    # Django 6.0+ has django.tasks built in; 5.2 needs the backport through the compat extra.
    tasks_db="django-tasks-db"
    [ "$version" = "5.2" ] && tasks_db="django-tasks-db[compat]"
    uv run --quiet --no-project --python "$PYTHON" \
        --with "django~=$version.0" \
        --with "psycopg[binary]" \
        --with pytest --with pytest-django \
        --with "$tasks_db" --with django-q2 --with djangorestframework \
        pytest --create-db -p no:cacheprovider \
        --junitxml="reports/django-$version.xml" "$@" || status=1
done
exit $status
