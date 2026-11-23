"""A background task for the tx- rules. Django 6.0+ ships django.tasks; 5.2 uses the backport."""

try:
    from django.tasks import task
except ImportError:
    from django_tasks import task


@task()
def mark_order_paid(payment_id):
    from labs.catalog.models import Payment

    Payment.objects.filter(pk=payment_id).update(status='processed')


def noop():
    """Target for the django-q2 tests; never executed, only enqueued."""
