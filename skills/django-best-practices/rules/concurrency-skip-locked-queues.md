---
title: Claim queue rows with skip_locked so workers do not wait on each other
impact: MEDIUM
risk: performance
django: ">=4.2"
database: postgresql
tags: select_for_update, skip_locked, nowait, queue, workers
sources:
  - https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-for-update
tests: test_concurrency_skip_locked_queues.py
---

## Claim queue rows with skip_locked so workers do not wait on each other

Workers that pick jobs with `select_for_update()` all lock the same first pending row:
one gets it and the rest wait until it commits, so adding workers adds no throughput.
`skip_locked=True` makes each worker skip rows already locked by another and take the
next one.

**Incorrect (every worker queues behind the first):**

```python
with transaction.atomic():
    job = Job.objects.select_for_update().filter(status='pending').order_by('pk').first()
    run(job)
```

**What happens:** the second worker's `SELECT ... FOR UPDATE` waits on the row the first
worker holds, for as long as that job runs.

**Correct (each worker claims a different row):**

```python
with transaction.atomic():
    job = (
        Job.objects.select_for_update(skip_locked=True)
        .filter(status='pending')
        .order_by('pk')
        .first()
    )
    if job is not None:
        run(job)
```

For work that should fail instead of waiting (a user action that must not queue behind a
long job), use `nowait=True`: the query raises `DatabaseError` at once if the row is
locked.

**When not to apply:** `skip_locked` returns an incomplete view of the table, which is
right for queues and wrong for anything that must see every row (reports, totals,
uniqueness checks). Holding the lock while the job runs keeps a transaction open for the
whole job; for long jobs, mark the row as taken in a short transaction and process it
afterwards. Before building a queue, consider an existing database-backed task queue.

**How to detect:** look for `select_for_update()` on status-filtered querysets used by
workers, cron jobs or management commands.

Reference: [QuerySet.select_for_update()](https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-for-update)
