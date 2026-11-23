"""tx-external-effects-on-commit, tx-nested-atomic-side-effects, tx-durable-entry-points,
tx-keep-short and tx-on-commit-bind-arguments.

A recording fake stands in for any effect outside the database (an email, an HTTP call,
a push notification): once sent it cannot be rolled back.
"""

import time
from functools import partial

import pytest
from django.db import OperationalError, connection, transaction

from labs.catalog.models import Payment
from tests.helpers import Session, lock_timeout

pytestmark = [pytest.mark.django_db(transaction=True)]


class Boom(Exception):
    pass


SENT = []


def notify(payment_id):
    """An external call, such as an email or a webhook to a partner."""
    SENT.append(f'payment {payment_id}')


@pytest.fixture
def sent():
    SENT.clear()
    yield SENT
    SENT.clear()


# tx-external-effects-on-commit


@pytest.mark.rule('tx-external-effects-on-commit')
def test_effect_sent_inside_the_transaction_survives_the_rollback(sent):
    with pytest.raises(Boom):
        with transaction.atomic():
            payment = Payment.objects.create(status='paid')
            notify(payment.pk)
            raise Boom

    assert Payment.objects.count() == 0
    assert len(sent) == 1  # The client was told about a payment that does not exist.


@pytest.mark.rule('tx-external-effects-on-commit')
def test_on_commit_drops_the_effect_on_rollback_and_sends_it_on_commit(sent):
    with pytest.raises(Boom):
        with transaction.atomic():
            payment = Payment.objects.create(status='paid')
            transaction.on_commit(partial(notify, payment.pk))
            raise Boom
    assert sent == []

    with transaction.atomic():
        payment = Payment.objects.create(status='paid')
        transaction.on_commit(partial(notify, payment.pk))
        assert sent == []  # Not yet: still inside the transaction.
    assert len(sent) == 1


@pytest.mark.rule('tx-external-effects-on-commit')
def test_on_commit_outside_a_transaction_runs_immediately(sent):
    assert not connection.in_atomic_block
    transaction.on_commit(partial(notify, 1))
    assert len(sent) == 1


# tx-nested-atomic-side-effects


def pay_then_notify(payment):
    """Looks safe: the email is sent after its own atomic block has exited."""
    with transaction.atomic():
        payment.status = 'paid'
        payment.save(update_fields=['status'])
    notify(payment.pk)


def pay_and_defer(payment):
    with transaction.atomic():
        payment.status = 'paid'
        payment.save(update_fields=['status'])
        transaction.on_commit(partial(notify, payment.pk))


@pytest.mark.rule('tx-nested-atomic-side-effects')
def test_exiting_a_nested_block_does_not_commit(sent):
    payments = [Payment.objects.create() for _ in range(3)]
    with pytest.raises(Boom):
        with transaction.atomic():  # A bulk caller wraps the single-item function.
            for payment in payments:
                pay_then_notify(payment)
            raise Boom

    assert Payment.objects.filter(status='paid').count() == 0
    assert len(sent) == 3


@pytest.mark.rule('tx-nested-atomic-side-effects')
def test_on_commit_waits_for_the_outermost_commit(sent):
    payments = [Payment.objects.create() for _ in range(3)]
    with pytest.raises(Boom):
        with transaction.atomic():
            for payment in payments:
                pay_and_defer(payment)
            raise Boom
    assert sent == []

    with transaction.atomic():
        for payment in payments:
            pay_and_defer(payment)
    assert len(sent) == 3


# tx-durable-entry-points


@pytest.mark.rule('tx-durable-entry-points')
def test_durable_block_refuses_to_be_nested():
    with pytest.raises(RuntimeError, match='durable'):
        with transaction.atomic():
            with transaction.atomic(durable=True):
                pass


@pytest.mark.django_db  # TestCase-style: the test itself runs inside a transaction.
@pytest.mark.rule('tx-durable-entry-points')
def test_durable_block_works_inside_testcase_transactions():
    with transaction.atomic(durable=True):
        Payment.objects.create()
    assert Payment.objects.count() == 1


@pytest.mark.rule('tx-durable-entry-points')
def test_durable_block_runs_at_the_top_level():
    with transaction.atomic(durable=True):
        Payment.objects.create()
    assert Payment.objects.count() == 1


# tx-keep-short


def slow_external_call():
    time.sleep(0.6)


@pytest.mark.rule('tx-keep-short')
def test_network_call_inside_the_transaction_keeps_the_row_locked():
    payment = Payment.objects.create()

    def pay_and_call(conn):
        with transaction.atomic():
            Payment.objects.filter(pk=payment.pk).update(status='paid')
            slow_external_call()  # The row lock is held for the whole call.

    with Session() as checkout:
        pending = checkout.submit(pay_and_call)
        time.sleep(0.1)
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            Payment.objects.filter(pk=payment.pk).update(status='refunded')
        Session.wait(pending)


@pytest.mark.rule('tx-keep-short')
def test_call_after_the_commit_releases_the_row_first():
    payment = Payment.objects.create()

    def pay_then_call(conn):
        with transaction.atomic():
            Payment.objects.filter(pk=payment.pk).update(status='paid')
        slow_external_call()

    with Session() as checkout:
        pending = checkout.submit(pay_then_call)
        time.sleep(0.1)
        with lock_timeout(300):
            Payment.objects.filter(pk=payment.pk).update(status='refunded')
        Session.wait(pending)


# tx-on-commit-bind-arguments


@pytest.mark.rule('tx-on-commit-bind-arguments')
def test_lambda_in_a_loop_sees_only_the_last_item(sent):
    payments = [Payment.objects.create() for _ in range(3)]
    with transaction.atomic():
        for payment in payments:
            transaction.on_commit(lambda: notify(payment.pk))

    assert set(sent) == {f'payment {payments[-1].pk}'}


@pytest.mark.rule('tx-on-commit-bind-arguments')
def test_partial_binds_each_item_when_registered(sent):
    payments = [Payment.objects.create() for _ in range(3)]
    with transaction.atomic():
        for payment in payments:
            transaction.on_commit(partial(notify, payment.pk))

    assert set(sent) == {f'payment {p.pk}' for p in payments}
