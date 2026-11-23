"""concurrency-select-for-update-of and concurrency-select-for-update-no-key."""

import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError

from labs.catalog.models import Product
from tests.helpers import Session, lock_timeout

pytestmark = [pytest.mark.django_db(transaction=True)]

User = get_user_model()


def deactivate(user):
    User.objects.filter(pk=user.pk).update(is_active=False)


@pytest.mark.rule('concurrency-select-for-update-of')
def test_select_related_locks_the_joined_rows_too(product, user):
    def lock(conn):
        return Product.objects.select_related('created_by').select_for_update().get(pk=product.pk)

    with Session() as editor, editor.atomic_hold(lock):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            deactivate(user)


@pytest.mark.rule('concurrency-select-for-update-of')
def test_of_self_locks_only_the_queryset_model(product, user):
    def lock(conn):
        return (
            Product.objects.select_related('created_by')
            .select_for_update(of=('self',))
            .get(pk=product.pk)
        )

    with Session() as editor, editor.atomic_hold(lock):
        with lock_timeout(300):
            deactivate(user)


def create_product_by(user, product):
    return Product.objects.create(name='plum', category=product.category, created_by=user)


@pytest.mark.rule('concurrency-select-for-update-no-key')
def test_for_update_blocks_inserts_that_reference_the_row(product, user):
    def lock(conn):
        return User.objects.select_for_update(of=('self',)).get(pk=user.pk)

    with Session() as editor, editor.atomic_hold(lock):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            create_product_by(user, product)


@pytest.mark.rule('concurrency-select-for-update-no-key')
def test_no_key_lets_referencing_inserts_through(product, user):
    def lock(conn):
        return User.objects.select_for_update(of=('self',), no_key=True).get(pk=user.pk)

    with Session() as editor, editor.atomic_hold(lock):
        with lock_timeout(300):
            create_product_by(user, product)


@pytest.mark.rule('concurrency-select-for-update-no-key')
def test_no_key_still_serializes_updates_of_the_row(user):
    def lock(conn):
        return User.objects.select_for_update(of=('self',), no_key=True).get(pk=user.pk)

    with Session() as editor, editor.atomic_hold(lock):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            deactivate(user)
