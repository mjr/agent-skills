"""concurrency-lock-on-fetch."""

import pytest

from labs.catalog.models import Product
from tests.helpers import Session

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('concurrency-lock-on-fetch')]


def rename(pk, name):
    Product.objects.filter(pk=pk).update(name=name)


def test_full_save_of_a_stale_instance_reverts_a_concurrent_change(product):
    stale = Product.objects.get(pk=product.pk)
    with Session() as other:
        other.run(lambda conn: rename(product.pk, 'pear'))

    stale.description = 'crisp'
    stale.save()  # Writes every column, including the old name.

    product.refresh_from_db()
    assert product.name == 'apple'


def test_update_fields_limits_the_damage_to_the_fields_you_changed(product):
    stale = Product.objects.get(pk=product.pk)
    with Session() as other:
        other.run(lambda conn: rename(product.pk, 'pear'))

    stale.description = 'crisp'
    stale.save(update_fields=['description'])

    product.refresh_from_db()
    assert (product.name, product.description) == ('pear', 'crisp')


def test_select_for_update_waits_and_then_reads_the_committed_row(product):
    def lock_and_rename(conn):
        locked = Product.objects.select_for_update(of=('self',)).get(pk=product.pk)
        locked.name = 'pear'
        locked.save(update_fields=['name'])

    def read_locked(conn):
        from django.db import transaction

        with transaction.atomic():
            return Product.objects.select_for_update(of=('self',)).get(pk=product.pk).name

    with Session() as first, Session() as second:
        with first.atomic_hold(lock_and_rename):
            pending = second.submit(read_locked)
            assert Session.is_running(pending), 'the second editor should wait for the lock'
        assert Session.wait(pending) == 'pear'
