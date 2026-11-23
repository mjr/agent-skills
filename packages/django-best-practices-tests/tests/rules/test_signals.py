"""signals- rules."""

import gc
import logging

import pytest
from django.conf import settings
from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import Job, Payment, Wallet

pytestmark = [pytest.mark.django_db(transaction=True)]


class Boom(Exception):
    pass


@pytest.fixture
def received():
    return []


# signals-send-robust-and-log


@pytest.mark.rule('signals-send-robust-and-log')
def test_send_propagates_a_receiver_error_and_skips_later_receivers(received):
    signal = Signal()

    def failing(**kwargs):
        raise Boom

    def later(**kwargs):
        received.append('later')

    signal.connect(failing, weak=False)
    signal.connect(later, weak=False)
    with pytest.raises(Boom):
        signal.send(sender=None)
    assert received == []


@pytest.mark.rule('signals-send-robust-and-log')
def test_send_robust_isolates_receivers_and_logs_the_error(received, caplog):
    signal = Signal()

    def failing(**kwargs):
        raise Boom

    def later(**kwargs):
        received.append('later')

    signal.connect(failing, weak=False)
    signal.connect(later, weak=False)
    with caplog.at_level(logging.ERROR, logger='django.dispatch'):
        responses = signal.send_robust(sender=None)

    assert received == ['later']
    assert isinstance(responses[0][1], Boom)
    assert any(r.name == 'django.dispatch' and r.exc_info for r in caplog.records)


# signals-dispatch-uid


def connect_closure(signal, received, **kwargs):
    def receiver(**signal_kwargs):
        received.append('called')

    signal.connect(receiver, weak=False, **kwargs)


@pytest.mark.rule('signals-dispatch-uid')
def test_the_same_function_object_is_connected_only_once(received):
    signal = Signal()

    def receiver(**kwargs):
        received.append('called')

    signal.connect(receiver, weak=False)
    signal.connect(receiver, weak=False)
    signal.send(sender=None)
    assert received == ['called']


@pytest.mark.rule('signals-dispatch-uid')
def test_new_function_objects_register_twice_without_dispatch_uid(received):
    signal = Signal()
    connect_closure(signal, received)  # e.g. a ready() or a factory that runs twice
    connect_closure(signal, received)
    signal.send(sender=None)
    assert received == ['called', 'called']


@pytest.mark.rule('signals-dispatch-uid')
def test_dispatch_uid_deduplicates_them(received):
    signal = Signal()
    connect_closure(signal, received, dispatch_uid='payments.notify')
    connect_closure(signal, received, dispatch_uid='payments.notify')
    signal.send(sender=None)
    assert received == ['called']


# signals-decouple-modules (weak references)


@pytest.mark.rule('signals-decouple-modules')
def test_weakly_connected_local_receiver_silently_disappears(received):
    signal = Signal()

    def register():
        def receiver(**kwargs):
            received.append('called')

        signal.connect(receiver)  # weak=True by default

    register()
    gc.collect()
    signal.send(sender=None)
    assert received == []


@pytest.mark.rule('signals-decouple-modules')
def test_bound_method_receiver_dies_with_its_instance(received):
    signal = Signal()

    class Handler:
        def on_event(self, **kwargs):
            received.append('called')

    signal.connect(Handler().on_event)
    gc.collect()
    signal.send(sender=None)
    assert received == []


# signals-receivers-exit-early


@pytest.mark.rule('signals-receivers-exit-early')
def test_post_save_without_sender_runs_for_every_model(received):
    def receiver(sender, **kwargs):
        received.append(sender.__name__)

    post_save.connect(receiver, weak=False, dispatch_uid='test-any-sender')
    try:
        Payment.objects.create()
        Wallet.objects.create()
        Job.objects.create()
    finally:
        post_save.disconnect(dispatch_uid='test-any-sender')
    assert received == ['Payment', 'Wallet', 'Job']


@pytest.mark.rule('signals-receivers-exit-early')
def test_sender_filter_and_early_return_avoid_wasted_queries(received):
    def lookup_everything(sender, instance, **kwargs):
        Payment.objects.filter(pk=instance.pk).exists()  # A query for every save.

    def exit_early(sender, instance, created, **kwargs):
        if not created or instance.status != 'paid':
            return
        received.append(instance.pk)

    post_save.connect(lookup_everything, weak=False, dispatch_uid='test-wasteful')
    with CaptureQueriesContext(connection) as wasteful:
        Wallet.objects.create()
    post_save.disconnect(dispatch_uid='test-wasteful')

    post_save.connect(exit_early, sender=Payment, weak=False, dispatch_uid='test-early')
    try:
        with CaptureQueriesContext(connection) as focused:
            Wallet.objects.create()  # Not connected for this sender: no call at all.
            Payment.objects.create(status='initiated')  # Called, returns at once.
    finally:
        post_save.disconnect(sender=Payment, dispatch_uid='test-early')

    assert len(wasteful.captured_queries) == 2  # The insert plus the receiver's query.
    assert len(focused.captured_queries) == 2  # Just the two inserts.
    assert received == []


# signals-run-in-sender-transaction


@pytest.mark.rule('signals-run-in-sender-transaction')
def test_receiver_writes_roll_back_with_the_sender():
    def audit(sender, instance, created, **kwargs):
        Job.objects.create(status=f'audit {instance.pk}')

    post_save.connect(audit, sender=Payment, weak=False, dispatch_uid='test-audit')
    try:
        with pytest.raises(Boom), transaction.atomic():
            Payment.objects.create()
            raise Boom
    finally:
        post_save.disconnect(sender=Payment, dispatch_uid='test-audit')
    assert Job.objects.count() == 0  # The audit row the receiver wrote is gone too.


@pytest.mark.rule('signals-run-in-sender-transaction')
def test_model_signal_receiver_error_aborts_the_save():
    def failing(sender, instance, **kwargs):
        raise Boom

    post_save.connect(failing, sender=Payment, weak=False, dispatch_uid='test-failing')
    try:
        with pytest.raises(Boom), transaction.atomic():
            Payment.objects.create()
    finally:
        post_save.disconnect(sender=Payment, dispatch_uid='test-failing')
    assert Payment.objects.count() == 0


# signals-bulk-operations-skip


@pytest.fixture
def saves(received):
    def receiver(sender, instance, **kwargs):
        received.append(('save', instance.pk))

    def deleted(sender, instance, **kwargs):
        received.append(('delete', instance.pk))

    post_save.connect(receiver, sender=Payment, weak=False, dispatch_uid='test-saves')
    post_delete.connect(deleted, sender=Payment, weak=False, dispatch_uid='test-deletes')
    yield received
    post_save.disconnect(sender=Payment, dispatch_uid='test-saves')
    post_delete.disconnect(sender=Payment, dispatch_uid='test-deletes')


@pytest.mark.rule('signals-bulk-operations-skip')
def test_bulk_create_bulk_update_and_update_send_no_save_signals(saves):
    payments = Payment.objects.bulk_create([Payment(), Payment()])
    for payment in payments:
        payment.status = 'paid'
    Payment.objects.bulk_update(payments, ['status'])
    Payment.objects.update(status='refunded')
    assert saves == []


@pytest.mark.rule('signals-bulk-operations-skip')
def test_queryset_delete_does_send_delete_signals_per_row(saves):
    payments = Payment.objects.bulk_create([Payment(), Payment()])
    with CaptureQueriesContext(connection) as ctx:
        Payment.objects.all().delete()
    assert sorted(saves) == sorted(('delete', p.pk) for p in payments)
    # With receivers connected, Django loads the rows first instead of a single DELETE.
    assert any(q['sql'].startswith('SELECT') for q in ctx.captured_queries)


# signals-serializable-args


@pytest.mark.rule('signals-serializable-args')
@pytest.mark.skipif(not settings.HAS_TASKS_DB, reason='django-tasks-db missing')
def test_task_queues_refuse_model_instances_as_arguments():
    from labs.catalog.tasks import mark_order_paid

    payment = Payment.objects.create()
    with pytest.raises((TypeError, ValueError)):
        mark_order_paid.enqueue(payment)
    mark_order_paid.enqueue(payment.pk)
