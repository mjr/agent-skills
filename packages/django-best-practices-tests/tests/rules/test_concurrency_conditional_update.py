"""concurrency-conditional-update."""

import pytest
from django.db import transaction
from django.db.models import F

from labs.catalog.models import Wallet
from tests.helpers import Session

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('concurrency-conditional-update')]


def withdraw_check_then_write(pk, amount):
    wallet = Wallet.objects.get(pk=pk)
    if wallet.balance < amount:
        return False
    wallet.balance -= amount
    wallet.save(update_fields=['balance'])
    return True


def withdraw_conditionally(pk, amount):
    return bool(
        Wallet.objects.filter(pk=pk, balance__gte=amount).update(balance=F('balance') - amount)
    )


def test_check_in_python_lets_both_withdrawals_through():
    wallet = Wallet.objects.create(balance=100)
    snapshot = Wallet.objects.get(pk=wallet.pk)  # This request has already read 100.
    with Session() as other:
        assert other.run(lambda conn: withdraw_check_then_write(wallet.pk, 80))

    assert snapshot.balance >= 80  # The stale check passes ...
    snapshot.balance -= 80
    snapshot.save(update_fields=['balance'])  # ... and 160 left a wallet that had 100.

    wallet.refresh_from_db()
    assert wallet.balance == 20


def test_condition_in_the_update_allows_exactly_one():
    wallet = Wallet.objects.create(balance=100)

    def first(conn):
        return withdraw_conditionally(wallet.pk, 80)

    with Session() as one, Session() as two:
        with one.atomic_hold(first) as succeeded:
            assert succeeded
            pending = two.submit(lambda conn: withdraw_conditionally(wallet.pk, 80))
            # The second UPDATE waits for the row, then re-checks the WHERE clause.
            assert Session.is_running(pending)
        assert Session.wait(pending) is False

    wallet.refresh_from_db()
    assert wallet.balance == 20


def test_select_for_update_also_works_but_holds_the_lock_while_python_decides():
    wallet = Wallet.objects.create(balance=100)

    def locked_withdraw(conn):
        with transaction.atomic():
            row = Wallet.objects.select_for_update(of=('self',), no_key=True).get(pk=wallet.pk)
            if row.balance < 80:
                return False
            row.balance = F('balance') - 80
            row.save(update_fields=['balance'])
            return True

    with Session() as one, Session() as two:
        assert one.run(locked_withdraw)
        assert two.run(locked_withdraw) is False

    wallet.refresh_from_db()
    assert wallet.balance == 20
