---
title: With a database-backed queue, enqueue critical tasks inside the transaction
impact: CRITICAL
risk: correctness
django: ">=5.2"
database: any
tags: tasks, queue, outbox, on_commit, django-tasks, django-q2, reliability
sources:
  - https://hakibenita.com/django-reliable-signals
tests: test_tx_enqueue_in_transaction.py
---

## With a database-backed queue, enqueue critical tasks inside the transaction

`on_commit()` prevents a task from running for data that was rolled back, but leaves a
gap: if the process dies between the commit and the callback (a deploy restart, a worker
killed by a timeout, out of memory), the data is saved and the task is never enqueued.
When the queue lives in the same database, enqueueing inside the transaction writes the
task row in that transaction: the task commits or rolls back with the data, and workers
cannot see it before the commit. This is the transactional outbox pattern.

**Incorrect for critical work (the task can be lost after the commit):**

```python
with transaction.atomic():
    payment.status = 'paid'
    payment.save(update_fields=['status'])
    transaction.on_commit(lambda pk=payment.pk: fulfil_order.enqueue(pk))
```

**What happens:** the payment is committed; any failure before the callback runs (an
earlier callback raising, the process being killed) means the order is never fulfilled,
and nothing records that it should have been.

**Correct (the task is part of the transaction):**

```python
with transaction.atomic():
    payment.status = 'paid'
    payment.save(update_fields=['status'])
    fulfil_order.enqueue(payment.pk)
```

Database-backed queues that behave this way:

- **Django tasks with django-tasks-db**: on Django 6.0+, `from django.tasks import task`
  and `TASKS = {'default': {'BACKEND': 'django_tasks_db.DatabaseBackend'}}` with
  `'django_tasks_db'` in `INSTALLED_APPS`. On Django 5.2, install
  `django-tasks-db[compat]`, which pulls in the `django-tasks` backport, and import
  `task` from `django_tasks`. Older guides use `django_tasks.backends.database` and an
  `ENQUEUE_ON_COMMIT` option; neither exists any more.
- **django-q2 with the ORM broker** (`Q_CLUSTER = {'orm': 'default', ...}`).

Conditions:

- **Same database.** The queue table must use the same connection as the data. With an
  external broker (Redis, RabbitMQ), enqueueing inside the transaction is wrong for the
  opposite reason: the worker can pick the task before the commit or after a rollback.
  Use `on_commit()` there.
- **Idempotent tasks.** Retries run a task more than once; it must tolerate that.
- **Serializable arguments.** Pass primary keys, not model instances.
- **Effects outside the database go inside the task.** The email or API call then only
  happens after the commit, and is retried if it fails.

**When not to apply:** for tasks whose loss is cheap or recoverable (a derived index that
a periodic job rebuilds), `on_commit()` is fine and keeps the queue independent of the
data's transaction.

**How to detect:** look for `transaction.on_commit(... .enqueue ...)`,
`on_commit(lambda: async_task(...))` and similar on flows where losing the task costs
money or leaves records stuck in an intermediate state. Testing backends hide the
difference: the immediate backend (and django-q2 with `sync=True`) runs the task at
enqueue time, inside the transaction, so tests cannot show what a worker sees. Test the
task's idempotency directly, by running it twice.

Reference: [Reliable Django Signals](https://hakibenita.com/django-reliable-signals)
