"""concurrency-skip-locked-queues."""

import pytest
from django.db import DatabaseError, OperationalError, transaction

from labs.catalog.models import Job
from tests.helpers import Session, lock_timeout

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('concurrency-skip-locked-queues')]


def claim(conn, **lock_options):
    job = Job.objects.select_for_update(**lock_options).filter(status='pending').order_by('pk').first()
    return job.pk if job else None


@pytest.fixture
def jobs():
    return [Job.objects.create().pk for _ in range(2)]


def test_plain_lock_makes_the_second_worker_wait(jobs):
    with Session() as worker, worker.atomic_hold(claim):
        with pytest.raises(OperationalError, match='lock timeout'), lock_timeout(300):
            with transaction.atomic():
                claim(None)


def test_skip_locked_hands_each_worker_a_different_job(jobs):
    with Session() as worker, worker.atomic_hold(lambda conn: claim(conn, skip_locked=True)) as first:
        with transaction.atomic():
            second = claim(None, skip_locked=True)
    assert {first, second} == set(jobs)


def test_nowait_fails_immediately_instead_of_waiting(jobs):
    with Session() as worker, worker.atomic_hold(claim):
        with pytest.raises(DatabaseError), transaction.atomic():
            claim(None, nowait=True)
