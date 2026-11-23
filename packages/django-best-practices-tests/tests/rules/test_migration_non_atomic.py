"""migration-isolate-non-atomic and migration-create-before-drop."""

import pytest
from django.db import ProgrammingError, connection, models

from labs.columnlab.models import Row
from tests.helpers import applied_migrations, column_names, index_names, migrate

pytestmark = [pytest.mark.django_db(transaction=True)]


@pytest.fixture
def failing_second_step(monkeypatch):
    migrate('nonatomic_lab', '0001')
    monkeypatch.setenv('DBP_FAIL_MIGRATION', '1')
    yield
    monkeypatch.delenv('DBP_FAIL_MIGRATION')
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE nonatomic_lab_note DROP COLUMN IF EXISTS tag')
    migrate('nonatomic_lab', '0002')


@pytest.mark.rule('migration-isolate-non-atomic')
def test_failure_leaves_earlier_operations_applied_and_the_migration_unrecorded(
    failing_second_step, monkeypatch
):
    with pytest.raises(RuntimeError, match='simulated failure'):
        migrate('nonatomic_lab', '0002')

    assert 'tag' in column_names('nonatomic_lab_note')  # The first operation stayed.
    assert '0002_add_tag' not in applied_migrations('nonatomic_lab')

    monkeypatch.delenv('DBP_FAIL_MIGRATION')
    with pytest.raises(ProgrammingError, match='already exists'):
        migrate('nonatomic_lab', '0002')  # Re-running repeats the first operation.
    monkeypatch.setenv('DBP_FAIL_MIGRATION', '1')


@pytest.mark.rule('migration-isolate-non-atomic')
def test_atomic_migration_rolls_everything_back():
    from labs.nonatomic_lab.models import Note

    field = models.CharField(max_length=20, null=True)
    field.set_attributes_from_name('extra')
    with pytest.raises(RuntimeError):
        with connection.schema_editor(atomic=True) as editor:
            editor.add_field(Note, field)
            raise RuntimeError('second operation failed')
    assert 'extra' not in column_names('nonatomic_lab_note')


FULL = models.Index(fields=['name'], name='row_name_full_ix')
PARTIAL = models.Index(
    fields=['name'], name='row_name_part_ix', condition=models.Q(name__startswith='a')
)


@pytest.fixture
def full_index():
    with connection.schema_editor(atomic=False) as editor:
        editor.add_index(Row, FULL, concurrently=True)
    yield
    with connection.cursor() as cursor:
        cursor.execute('DROP INDEX IF EXISTS row_name_full_ix')
        cursor.execute('DROP INDEX IF EXISTS row_name_part_ix')


class Interrupted(Exception):
    pass


@pytest.mark.rule('migration-create-before-drop')
def test_drop_first_leaves_no_index_when_interrupted(full_index):
    with pytest.raises(Interrupted), connection.schema_editor(atomic=False) as editor:
        editor.remove_index(Row, FULL, concurrently=True)
        raise Interrupted  # The process dies before the replacement is built.
    assert index_names('columnlab_row') & {'row_name_full_ix', 'row_name_part_ix'} == set()


@pytest.mark.rule('migration-create-before-drop')
def test_create_first_always_leaves_an_index(full_index):
    with pytest.raises(Interrupted), connection.schema_editor(atomic=False) as editor:
        editor.add_index(Row, PARTIAL, concurrently=True)
        raise Interrupted  # The process dies before the old index is dropped.
    assert {'row_name_full_ix', 'row_name_part_ix'} <= index_names('columnlab_row')
