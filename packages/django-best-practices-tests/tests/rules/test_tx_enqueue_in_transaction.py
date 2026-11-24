"""tx-enqueue-in-transaction-db-queue and tx-on-commit-robust.

With a queue stored in the same database, enqueueing inside the transaction makes the
task commit or roll back together with the data. Deferring with on_commit leaves a gap:
the data commits and the task can still be lost.
"""

import unittest
from functools import partial

import django
import pytest
from django.conf import settings
from django.db import transaction

from labs.catalog.models import Payment
from tests.helpers import Session, execute

pytestmark = [pytest.mark.django_db(transaction=True)]

needs_tasks_db = pytest.mark.skipif(not settings.HAS_TASKS_DB, reason='django-tasks-db missing')
needs_django_q = pytest.mark.skipif(not settings.HAS_DJANGO_Q, reason='django-q2 missing')


class Boom(Exception):
    pass


def queued_tasks():
    from django_tasks_db.models import DBTaskResult

    return DBTaskResult.objects.count()


def enqueue(payment):
    from labs.catalog.tasks import mark_order_paid

    mark_order_paid.enqueue(payment.pk)


@needs_tasks_db
@pytest.mark.rule('tx-enqueue-in-transaction-db-queue')
def test_task_rolls_back_with_the_data():
    with pytest.raises(Boom):
        with transaction.atomic():
            enqueue(Payment.objects.create(status='paid'))
            raise Boom

    assert Payment.objects.count() == 0
    assert queued_tasks() == 0


@needs_tasks_db
@pytest.mark.rule('tx-enqueue-in-transaction-db-queue')
def test_workers_only_see_the_task_after_commit():
    with Session() as worker:
        with transaction.atomic():
            enqueue(Payment.objects.create(status='paid'))
            seen = worker.run(execute('SELECT count(*) FROM django_tasks_database_dbtaskresult'))
            assert seen == [(0,)], 'an uncommitted task must be invisible to workers'
        seen = worker.run(execute('SELECT count(*) FROM django_tasks_database_dbtaskresult'))
    assert seen == [(1,)]


@needs_tasks_db
@pytest.mark.rule('tx-enqueue-in-transaction-db-queue')
def test_on_commit_can_lose_the_task_after_the_data_commits():
    """A failure between the commit and the deferred enqueue loses the task for good.

    A crash or a killed worker process has the same effect; a failing earlier callback
    is just the simplest way to reproduce it in a test.
    """
    with pytest.raises(ZeroDivisionError):
        with transaction.atomic():
            payment = Payment.objects.create(status='paid')
            transaction.on_commit(lambda: 1 / 0)
            transaction.on_commit(lambda: enqueue(payment))

    assert Payment.objects.filter(status='paid').count() == 1
    assert queued_tasks() == 0


@needs_tasks_db
@pytest.mark.rule('tx-on-commit-robust')
def test_robust_callback_does_not_stop_the_next_one():
    with transaction.atomic():
        payment = Payment.objects.create(status='paid')
        transaction.on_commit(lambda: 1 / 0, robust=True)
        transaction.on_commit(lambda: enqueue(payment))

    assert queued_tasks() == 1


@needs_tasks_db
@pytest.mark.rule('tx-on-commit-robust')
def test_robust_callback_error_is_logged_not_raised(caplog):
    with transaction.atomic():
        transaction.on_commit(lambda: 1 / 0, robust=True)
    assert any('on_commit' in r.getMessage() and r.exc_info for r in caplog.records)


def failing_send(pk):
    raise Boom(pk)


@pytest.mark.rule('tx-on-commit-robust')
@pytest.mark.skipif(django.VERSION >= (6, 1), reason='Fixed in Django 6.1')
def test_robust_partial_raises_instead_of_logging_before_6_1():
    """Django 5.2 and 6.0 log a robust failure with func.__qualname__, which partial lacks.

    The AttributeError escapes after the commit: the data is saved, the caller gets a 500,
    and the callbacks registered after it do not run.
    """
    ran = []
    with pytest.raises(AttributeError, match='__qualname__'):
        with transaction.atomic():
            Payment.objects.create(status='paid')
            transaction.on_commit(partial(failing_send, 1), robust=True)
            transaction.on_commit(lambda: ran.append('next'), robust=True)
    assert Payment.objects.count() == 1
    assert ran == []


@pytest.mark.rule('tx-on-commit-robust')
@pytest.mark.skipif(django.VERSION < (6, 1), reason='Raises before Django 6.1')
def test_robust_partial_is_logged_from_6_1(caplog):
    with transaction.atomic():
        transaction.on_commit(partial(failing_send, 1), robust=True)
    assert any('on_commit' in r.getMessage() and r.exc_info for r in caplog.records)


@pytest.mark.rule('tx-on-commit-robust')
@pytest.mark.parametrize('in_transaction', [True, False])
def test_robust_lambda_with_bound_argument_is_logged_on_every_version(caplog, in_transaction):
    payment = Payment.objects.create(status='paid')
    callback = lambda pk=payment.pk: failing_send(pk)  # noqa: E731
    if in_transaction:
        with transaction.atomic():
            transaction.on_commit(callback, robust=True)
    else:
        transaction.on_commit(callback, robust=True)  # Runs immediately, still robust.
    assert any('on_commit' in r.getMessage() and r.exc_info for r in caplog.records)


@pytest.mark.rule('tx-on-commit-robust')
@pytest.mark.skipif(django.VERSION >= (6, 1), reason='Fixed in Django 6.1')
@pytest.mark.django_db(transaction=False)  # TestCase-style: callbacks are only captured.
def test_capture_on_commit_callbacks_raises_the_same_way_before_6_1(django_capture_on_commit_callbacks):
    """Tests hit the same bug, so a test that expects the failure to be logged errors."""
    with pytest.raises(AttributeError, match='__qualname__'):
        with django_capture_on_commit_callbacks(execute=True):
            transaction.on_commit(partial(failing_send, 1), robust=True)


@pytest.mark.rule('tx-on-commit-robust')
@pytest.mark.django_db(transaction=False)  # TestCase-style: callbacks are only captured.
def test_capture_on_commit_callbacks_logs_robust_failures_to_django_test(django_capture_on_commit_callbacks):
    """On a real commit the logger is django.db.backends.base; under capture it is django.test."""
    case = unittest.TestCase()
    with case.assertLogs('django.test', level='ERROR') as logs:
        with django_capture_on_commit_callbacks(execute=True):
            transaction.on_commit(lambda pk=1: failing_send(pk), robust=True)
    assert 'on_commit' in logs.output[0]
    with pytest.raises(AssertionError, match='no logs'):
        with case.assertLogs('django.db.backends.base', level='ERROR'):
            with django_capture_on_commit_callbacks(execute=True):
                transaction.on_commit(lambda pk=1: failing_send(pk), robust=True)


@pytest.mark.rule('tx-on-commit-robust')
def test_real_commit_logs_robust_failures_to_django_db_backends_base():
    case = unittest.TestCase()
    with case.assertLogs('django.db.backends.base', level='ERROR'):
        with transaction.atomic():
            transaction.on_commit(lambda pk=1: failing_send(pk), robust=True)


@pytest.mark.rule('tx-on-commit-robust')
def test_plain_callback_error_reaches_the_caller_after_the_commit():
    """The data is committed, yet the caller sees an exception (a 500 in a view)."""
    with pytest.raises(ZeroDivisionError):
        with transaction.atomic():
            Payment.objects.create(status='paid')
            transaction.on_commit(lambda: 1 / 0)
    assert Payment.objects.count() == 1


@needs_tasks_db
@pytest.mark.rule('tx-enqueue-in-transaction-db-queue')
def test_immediate_backend_runs_the_task_before_the_commit():
    """The usual test backend runs tasks at enqueue time, inside the transaction.

    Tests on it pass even if the code relies on the task seeing committed data, and they
    cannot show what a worker would see; test idempotency separately.
    """
    from django.test import override_settings

    try:
        import django.tasks  # noqa: F401

        backend = 'django.tasks.backends.immediate.ImmediateBackend'
    except ImportError:
        backend = 'django_tasks.backends.immediate.ImmediateBackend'

    with override_settings(TASKS={'default': {'BACKEND': backend}}):
        with pytest.raises(Boom):
            with transaction.atomic():
                payment = Payment.objects.create(status='paid')
                enqueue(payment)
                payment.refresh_from_db()
                assert payment.status == 'processed'  # Already ran, uncommitted.
                raise Boom
    assert Payment.objects.count() == 0


@needs_django_q
@pytest.mark.rule('tx-enqueue-in-transaction-db-queue')
def test_django_q_orm_broker_is_transactional_too():
    from django_q.models import OrmQ
    from django_q.tasks import async_task

    with pytest.raises(Boom):
        with transaction.atomic():
            async_task('labs.catalog.tasks.noop')
            raise Boom
    assert OrmQ.objects.count() == 0

    with transaction.atomic():
        async_task('labs.catalog.tasks.noop')
    assert OrmQ.objects.count() == 1
