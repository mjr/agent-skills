"""migration-deploy-compatible.

During a deploy the old code keeps running against the new schema (or the new code
against the old one). Removing a column in the same release that stops using it breaks
whichever side runs second.
"""

import pytest
from django.db import IntegrityError, ProgrammingError, connection

from labs.columnlab.models import Row, RowNextRelease

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-deploy-compatible')]

LEGACY = Row._meta.get_field('legacy')


@pytest.fixture(autouse=True)
def restore_legacy():
    yield
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE columnlab_row ADD COLUMN IF NOT EXISTS legacy varchar(50) NOT NULL DEFAULT 'x'"
        )
        cursor.execute('ALTER TABLE columnlab_row ALTER COLUMN legacy DROP DEFAULT')
        cursor.execute("UPDATE columnlab_row SET legacy = 'x' WHERE legacy IS NULL")
        cursor.execute('ALTER TABLE columnlab_row ALTER COLUMN legacy SET NOT NULL')


def test_old_code_breaks_once_the_column_is_dropped():
    Row.objects.create(name='a')
    with connection.schema_editor() as editor:
        editor.remove_field(Row, LEGACY)
    with pytest.raises(ProgrammingError, match='legacy'):
        list(Row.objects.all())  # Old code still selects every column it knows.


def test_new_code_cannot_insert_while_the_old_column_is_still_not_null():
    with pytest.raises(IntegrityError, match='legacy'):
        RowNextRelease.objects.create(name='a')


def test_making_the_column_nullable_first_lets_both_versions_run():
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE columnlab_row ALTER COLUMN legacy DROP NOT NULL')
    RowNextRelease.objects.create(name='new code')
    Row.objects.create(name='old code')
    assert Row.objects.count() == 2
