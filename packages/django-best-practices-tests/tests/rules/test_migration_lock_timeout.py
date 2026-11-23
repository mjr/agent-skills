"""migration-lock-timeout.

ALTER TABLE needs an ACCESS EXCLUSIVE lock. While it waits behind any open transaction
that touched the table, every later query on that table queues behind it, so a migration
that merely waits takes the table offline. A lock_timeout makes it fail fast instead.
"""

import pytest
from django.db import OperationalError, connection, models
from django.db.backends.postgresql.base import DatabaseWrapper

from labs.locklab.models import Ledger
from tests.helpers import Session, execute, lock_timeout

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-lock-timeout')]


def add_column(conn, lock_ms=None):
    field = models.IntegerField(null=True)
    field.set_attributes_from_name('extra')
    with conn.schema_editor() as editor:
        if lock_ms is not None:
            # The in-migration variant: scoped to the migration's own transaction.
            editor.execute(f'SET LOCAL lock_timeout = {int(lock_ms)}')
        editor.add_field(Ledger, field)


def drop_column_if_present():
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE locklab_ledger DROP COLUMN IF EXISTS extra')


@pytest.fixture
def open_reader():
    """Another request that read the table and has not finished its transaction yet."""
    with Session() as reader:
        reader.run(execute('BEGIN'))
        reader.run(execute('SELECT count(*) FROM locklab_ledger'))
        yield reader
        reader.run(execute('COMMIT'))
    drop_column_if_present()


def test_waiting_migration_blocks_later_readers(open_reader):
    with Session() as migration:
        pending = migration.submit(lambda conn: add_column(conn))
        assert Session.is_running(pending), 'the ALTER TABLE should be waiting for the lock'

        # A plain read that arrives now queues behind the waiting ALTER TABLE.
        with pytest.raises(OperationalError, match='lock timeout'):
            with lock_timeout(300):
                list(Ledger.objects.all())

        open_reader.run(execute('COMMIT'))
        open_reader.run(execute('BEGIN'))  # Keeps the fixture teardown valid.
        Session.wait(pending)


def test_set_local_lock_timeout_makes_the_migration_fail_fast(open_reader):
    with Session() as migration:
        with pytest.raises(OperationalError, match='lock timeout'):
            migration.run(lambda conn: add_column(conn, lock_ms=300))

    # Readers are not stuck behind it.
    with lock_timeout(300):
        assert list(Ledger.objects.all()) == []


def test_lock_timeout_through_connection_options_needs_no_runsql():
    """The connection-level variant: only the process that runs migrate sets it."""
    settings_dict = {**connection.settings_dict, 'OPTIONS': {'options': '-c lock_timeout=4000'}}
    # A separate connection object; the alias only has to be a configured one.
    wrapper = DatabaseWrapper(settings_dict, alias='default')
    try:
        with wrapper.cursor() as cursor:
            cursor.execute('SHOW lock_timeout')
            assert cursor.fetchone()[0] == '4s'
    finally:
        wrapper.close()
