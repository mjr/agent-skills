"""migration-concurrent-indexes."""

import pytest
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import NotSupportedError, OperationalError, ProgrammingError, connection, models
from django.db.migrations.loader import MigrationLoader

from labs.columnlab.models import Row
from tests.helpers import Session, execute, index_names, lock_timeout

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-concurrent-indexes')]

INDEX = models.Index(fields=['name'], name='row_name_ix')


@pytest.fixture(autouse=True)
def no_index():
    yield
    with connection.cursor() as cursor:
        cursor.execute('DROP INDEX IF EXISTS row_name_ix')


def add_index(conn, concurrently):
    with conn.schema_editor(atomic=not concurrently) as editor:
        editor.add_index(Row, INDEX, concurrently=concurrently)


def index_is_valid(name):
    with connection.cursor() as cursor:
        cursor.execute('SELECT indisvalid FROM pg_index WHERE indexrelid = %s::regclass', [name])
        return cursor.fetchone()[0]


def test_plain_create_index_blocks_writes_until_the_migration_commits():
    with Session() as migration, migration.atomic_hold(lambda conn: add_index(conn, False)):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            Row.objects.create(name='new')


def test_concurrent_build_lets_writes_through():
    with Session() as reader, Session() as builder:
        # A transaction that wrote to the table and is still open makes the concurrent
        # build wait for it, so the build is still running while this test writes.
        reader.run(execute('BEGIN'))
        reader.run(execute("INSERT INTO columnlab_row (name, legacy) VALUES ('w', 'x')"))
        pending = builder.submit(lambda conn: add_index(conn, True))
        assert Session.is_running(pending)

        with lock_timeout(300):
            Row.objects.create(name='new')

        reader.run(execute('COMMIT'))
        Session.wait(pending)
    assert index_is_valid('row_name_ix')


def test_add_index_concurrently_refuses_to_run_in_a_transaction():
    operation = AddIndexConcurrently('row', INDEX)
    from_state = MigrationLoader(connection).project_state()
    to_state = from_state.clone()
    operation.state_forwards('columnlab', to_state)
    with pytest.raises(NotSupportedError, match='atomic = False'):
        with connection.schema_editor(atomic=True) as editor:
            operation.database_forwards('columnlab', editor, from_state, to_state)


def test_interrupted_concurrent_build_leaves_an_invalid_index_that_blocks_a_retry():
    with Session() as reader, Session() as builder:
        reader.run(execute('BEGIN'))
        reader.run(execute("INSERT INTO columnlab_row (name, legacy) VALUES ('w', 'x')"))
        builder.run(execute('SET statement_timeout = 300'))
        with pytest.raises(OperationalError, match='statement timeout'):
            builder.run(lambda conn: add_index(conn, True))
        reader.run(execute('COMMIT'))

    assert 'row_name_ix' in index_names('columnlab_row')
    assert not index_is_valid('row_name_ix')  # Present, unusable, still maintained on writes.

    with pytest.raises(ProgrammingError, match='already exists'):
        add_index(connection, True)  # Re-running the migration fails.


def test_plain_drop_index_blocks_reads_too():
    add_index(connection, True)

    def drop(conn):
        with conn.cursor() as cursor:
            cursor.execute('DROP INDEX row_name_ix')

    with Session() as migration, migration.atomic_hold(drop):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            list(Row.objects.all())


@pytest.mark.rule('migration-lock-timeout')
def test_short_lock_timeout_makes_concurrent_builds_fail_while_they_wait():
    with Session() as reader, Session() as builder:
        reader.run(execute('BEGIN'))
        reader.run(execute("INSERT INTO columnlab_row (name, legacy) VALUES ('w', 'x')"))
        builder.run(execute('SET lock_timeout = 300'))
        with pytest.raises(OperationalError, match='lock timeout'):
            builder.run(lambda conn: add_index(conn, True))
        reader.run(execute('COMMIT'))
