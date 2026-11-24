"""migration-set-not-null-in-steps.

SET NOT NULL scans the whole table under an ACCESS EXCLUSIVE lock. On PostgreSQL 12+, a
validated CHECK (col IS NOT NULL) constraint lets it skip the scan, and the CHECK can be
validated without blocking writes.
"""

import pytest
from django.db import OperationalError, connection

from labs.nonatomic_lab.models import Note
from tests.helpers import Session, lock_timeout

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-set-not-null-in-steps')]


@pytest.fixture(autouse=True)
def restore_tag_column():
    yield
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE nonatomic_lab_note DROP CONSTRAINT IF EXISTS note_tag_not_null')
        cursor.execute('ALTER TABLE nonatomic_lab_note ALTER COLUMN tag DROP NOT NULL')


def test_alterfield_to_not_null_is_a_plain_set_not_null():
    old = Note._meta.get_field('tag')
    new = old.clone()
    new.null = False
    new.set_attributes_from_name('tag')
    new.model = Note
    with connection.schema_editor(collect_sql=True) as editor:
        editor.alter_field(Note, old, new)
    sql = ' '.join(editor.collected_sql)
    assert 'SET NOT NULL' in sql
    assert 'NOT VALID' not in sql


def server_messages(statements):
    """Run statements at DEBUG1 and return the server's debug messages."""
    messages = []
    raw = connection.connection
    handler = lambda diag: messages.append(diag.message_primary)  # noqa: E731
    raw.add_notice_handler(handler)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SET client_min_messages = debug1')
            for statement in statements:
                cursor.execute(statement)
            cursor.execute('SET client_min_messages = notice')
    finally:
        raw.remove_notice_handler(handler)
    return messages


def test_set_not_null_scans_the_table_without_a_check_constraint():
    Note.objects.create(text='a', tag='x')
    messages = server_messages(['ALTER TABLE nonatomic_lab_note ALTER COLUMN tag SET NOT NULL'])
    assert any('verifying table' in m for m in messages)


def test_validated_check_constraint_lets_set_not_null_skip_the_scan():
    Note.objects.create(text='a', tag='x')
    with connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE nonatomic_lab_note ADD CONSTRAINT note_tag_not_null '
            'CHECK (tag IS NOT NULL) NOT VALID'
        )
        cursor.execute('ALTER TABLE nonatomic_lab_note VALIDATE CONSTRAINT note_tag_not_null')
    messages = server_messages(['ALTER TABLE nonatomic_lab_note ALTER COLUMN tag SET NOT NULL'])
    assert any('sufficient to prove' in m for m in messages)
    assert not any('verifying table' in m for m in messages)


ADD_CHECK = (
    'ALTER TABLE nonatomic_lab_note ADD CONSTRAINT note_tag_not_null '
    'CHECK (tag IS NOT NULL) NOT VALID'
)
VALIDATE = 'ALTER TABLE nonatomic_lab_note VALIDATE CONSTRAINT note_tag_not_null'


def run(*statements):
    def job(conn):
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    return job


def test_not_valid_and_validate_in_one_migration_keep_the_table_locked():
    """An atomic migration runs both in one transaction: ADD CONSTRAINT's ACCESS
    EXCLUSIVE lock is held until the commit, so the VALIDATE scan runs under it and
    even reads wait."""
    Note.objects.create(text='a', tag='x')
    with Session() as migration, migration.atomic_hold(run(ADD_CHECK, VALIDATE)):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            list(Note.objects.all())
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            Note.objects.create(text='b', tag='y')


def test_validate_in_its_own_migration_lets_reads_and_writes_through():
    Note.objects.create(text='a', tag='x')
    run(ADD_CHECK)(connection)  # The previous migration, already committed.
    with Session() as migration, migration.atomic_hold(run(VALIDATE)):
        with lock_timeout(300):
            list(Note.objects.all())
            Note.objects.create(text='b', tag='y')
