"""migration-fk-not-valid.

Adding a foreign key constraint to a populated column validates every row while holding a
SHARE ROW EXCLUSIVE lock on both tables, which blocks their writes. NOT VALID plus a
separate VALIDATE CONSTRAINT checks the rows without blocking writes.
"""

import pytest
from django.db import IntegrityError, OperationalError, connection

from labs.columnlab.models import Item, Owner
from tests.helpers import Session, lock_timeout, migrate, sqlmigrate

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-fk-not-valid')]

ADD_FK = (
    'ALTER TABLE columnlab_item ADD CONSTRAINT item_owner_fk '
    'FOREIGN KEY (owner_ref) REFERENCES columnlab_owner (id)'
)


@pytest.fixture(autouse=True)
def items():
    owner = Owner.objects.create(name='o')
    Item.objects.bulk_create(Item(owner_ref=owner.pk) for _ in range(5))
    yield owner
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE columnlab_item DROP CONSTRAINT IF EXISTS item_owner_fk')


def run(sql):
    def job(conn):
        with conn.cursor() as cursor:
            cursor.execute(sql)

    return job


def test_plain_add_constraint_blocks_writes_to_both_tables(items):
    with Session() as migration, migration.atomic_hold(run(ADD_FK)):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            Owner.objects.create(name='new')
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            Item.objects.create(owner_ref=items.pk)


def test_validate_constraint_lets_writes_through(items):
    run(ADD_FK + ' NOT VALID')(connection)
    validate = run('ALTER TABLE columnlab_item VALIDATE CONSTRAINT item_owner_fk')
    with Session() as migration, migration.atomic_hold(validate):
        with lock_timeout(300):
            Owner.objects.create(name='new')
            Item.objects.create(owner_ref=items.pk)


def test_not_valid_constraint_still_rejects_new_bad_rows():
    run(ADD_FK + ' NOT VALID')(connection)
    with pytest.raises(IntegrityError):
        Item.objects.create(owner_ref=999_999)


def test_django_generated_foreign_keys_are_never_not_valid():
    migrate('fk_naive', '0001')
    try:
        sql = sqlmigrate('fk_naive', '0002')
    finally:
        migrate('fk_naive', '0002')
    assert 'FOREIGN KEY' in sql
    assert 'NOT VALID' not in sql
