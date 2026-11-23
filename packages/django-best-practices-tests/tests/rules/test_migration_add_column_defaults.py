"""migration-add-column-defaults.

PostgreSQL 11+ adds a column with a non-volatile default without rewriting the table.
A volatile database default (gen_random_uuid(), random()) rewrites every row. A Python
default is evaluated once by Django, so every existing row gets the same value.
"""

import uuid

import pytest
from django.contrib.postgres.functions import RandomUUID
from django.db import connection, models
from django.db.models.functions import Now

from labs.columnlab.models import Row
from tests.helpers import relfilenode

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-add-column-defaults')]


@pytest.fixture
def rows():
    return [Row.objects.create(name=f'row {i}') for i in range(3)]


def add_column(field, name='added'):
    field.set_attributes_from_name(name)
    field.model = Row
    with connection.schema_editor() as editor:
        editor.add_field(Row, field)
    return field


@pytest.fixture(autouse=True)
def drop_added_column():
    yield
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE columnlab_row DROP COLUMN IF EXISTS added')


def values():
    with connection.cursor() as cursor:
        cursor.execute('SELECT added FROM columnlab_row')
        return [row[0] for row in cursor.fetchall()]


def test_python_default_gives_every_existing_row_the_same_value(rows):
    before = relfilenode('columnlab_row')
    add_column(models.UUIDField(default=uuid.uuid4))

    assert len(set(values())) == 1  # One uuid4() call for the whole table.
    assert relfilenode('columnlab_row') == before  # Fast: no table rewrite.


def test_python_default_is_dropped_from_the_database_afterwards(rows):
    add_column(models.IntegerField(default=0))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'columnlab_row' AND column_name = 'added'"
        )
        assert cursor.fetchone()[0] is None  # Inserts that omit the column will fail.


def test_non_volatile_db_default_does_not_rewrite(rows):
    before = relfilenode('columnlab_row')
    add_column(models.DateTimeField(db_default=Now()))

    assert len(set(values())) == 1
    assert relfilenode('columnlab_row') == before


def test_volatile_db_default_rewrites_the_table(rows):
    before = relfilenode('columnlab_row')
    add_column(models.UUIDField(db_default=RandomUUID()))

    assert len(set(values())) == 3  # Computed per row ...
    assert relfilenode('columnlab_row') != before  # ... by rewriting the whole table.
