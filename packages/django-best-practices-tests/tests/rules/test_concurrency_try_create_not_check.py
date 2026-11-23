"""concurrency-try-create-not-check."""

import pytest
from django.db import IntegrityError, transaction
from django.db.transaction import TransactionManagementError

from labs.catalog.models import ShortUrl
from tests.helpers import Session

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('concurrency-try-create-not-check')]


def test_check_then_create_races():
    """Both requests pass the exists() check before either inserts."""
    with Session() as other:
        assert not other.run(lambda conn: ShortUrl.objects.filter(key='k').exists())
        assert not ShortUrl.objects.filter(key='k').exists()

        other.run(lambda conn: ShortUrl.objects.create(key='k', target_url='https://a.example'))
        with pytest.raises(IntegrityError):
            ShortUrl.objects.create(key='k', target_url='https://b.example')


def test_catching_integrity_error_without_a_savepoint_breaks_the_transaction():
    ShortUrl.objects.create(key='k', target_url='https://a.example')
    with pytest.raises(TransactionManagementError):
        with transaction.atomic():
            ShortUrl.objects.create(key='other', target_url='https://b.example')
            try:
                ShortUrl.objects.create(key='k', target_url='https://c.example')
            except IntegrityError:
                pass
            ShortUrl.objects.count()  # Refused: the transaction is aborted.


def test_savepoint_keeps_the_outer_transaction_usable():
    ShortUrl.objects.create(key='k', target_url='https://a.example')
    with transaction.atomic():
        ShortUrl.objects.create(key='other', target_url='https://b.example')
        try:
            with transaction.atomic():
                ShortUrl.objects.create(key='k', target_url='https://c.example')
        except IntegrityError:
            pass
        assert ShortUrl.objects.count() == 2
    assert ShortUrl.objects.filter(key='other').exists()


def test_the_driver_reports_which_constraint_failed():
    ShortUrl.objects.create(key='k', target_url='https://a.example')
    try:
        with transaction.atomic():
            ShortUrl.objects.create(key='k', target_url='https://b.example')
    except IntegrityError as error:
        constraint = error.__cause__.diag.constraint_name
    assert 'key' in constraint
