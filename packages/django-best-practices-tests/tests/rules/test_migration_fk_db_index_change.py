"""migration-fk-db-index-change and migration-review-sql.

Turning db_index off on an existing ForeignKey makes the generated AlterField drop and
re-create the whole constraint. SeparateDatabaseAndState + RunSQL drops only the index.
"""

import io

import pytest
from django.core.management import call_command

from tests.helpers import foreign_key_oids, index_names, migrate, sqlmigrate

pytestmark = [pytest.mark.django_db(transaction=True)]


@pytest.fixture
def at_initial_state():
    """Put both labs at 0001 and restore the latest state afterwards."""
    migrate('fk_naive', '0001')
    migrate('fk_safe', '0001')
    yield
    migrate('fk_naive', '0002')
    migrate('fk_safe', '0002')


@pytest.mark.rule('migration-fk-db-index-change')
def test_generated_alterfield_recreates_the_constraint(at_initial_state):
    sql = sqlmigrate('fk_naive', '0002')
    assert 'DROP CONSTRAINT' in sql
    assert 'ADD CONSTRAINT' in sql

    before = foreign_key_oids('fk_naive_child')
    migrate('fk_naive', '0002')
    after = foreign_key_oids('fk_naive_child')

    assert before.keys() == after.keys()
    # Same constraint name, new object: it was dropped and validated again from scratch.
    assert before != after
    assert 'fk_naive_child_parent_id_4b951ec7' not in index_names('fk_naive_child')


@pytest.mark.rule('migration-fk-db-index-change')
def test_separate_database_and_state_drops_only_the_index(at_initial_state):
    sql = sqlmigrate('fk_safe', '0002')
    assert 'DROP INDEX CONCURRENTLY' in sql
    assert 'CONSTRAINT' not in sql

    before = foreign_key_oids('fk_safe_child')
    migrate('fk_safe', '0002')

    assert foreign_key_oids('fk_safe_child') == before
    assert 'fk_safe_child_parent_id_7e074e51' not in index_names('fk_safe_child')


@pytest.mark.rule('migration-reversible')
def test_safe_migration_is_reversible(at_initial_state):
    migrate('fk_safe', '0002')
    migrate('fk_safe', '0001')
    assert 'fk_safe_child_parent_id_7e074e51' in index_names('fk_safe_child')


@pytest.mark.rule('migration-fk-db-index-change')
def test_safe_migration_keeps_django_state_in_sync():
    # makemigrations --check exits non-zero if the state operations miss anything.
    call_command('makemigrations', 'fk_safe', '--check', '--dry-run', stdout=io.StringIO())


@pytest.mark.rule('migration-review-sql')
def test_sqlmigrate_hides_constraint_changes_on_an_unmigrated_database():
    """sqlmigrate reads constraint names from the live database.

    Against a database where the table does not exist yet, it prints no SQL for the
    AlterField, so the review must run against a database migrated up to the previous
    migration (a copy of production, or a local database at the same state).
    """
    migrate('fk_naive', 'zero')
    try:
        assert '(no-op)' in sqlmigrate('fk_naive', '0002')
    finally:
        migrate('fk_naive', '0002')
