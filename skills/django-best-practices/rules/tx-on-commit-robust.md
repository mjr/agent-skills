---
title: Use on_commit(robust=True) for independent best-effort callbacks
impact: MEDIUM
risk: correctness
django: ">=4.2"
database: any
tags: on_commit, robust, callbacks, errors
sources:
  - https://docs.djangoproject.com/en/stable/topics/db/transactions/#django.db.transaction.on_commit
tests: test_tx_enqueue_in_transaction.py
---

## Use on_commit(robust=True) for independent best-effort callbacks

Callbacks registered with `on_commit()` run in order after the commit. When one raises,
the remaining callbacks never run, and the exception reaches the caller even though the
data is already committed: a view returns a 500 for an operation that succeeded, and
later callbacks (a second email, a cache invalidation, an enqueue) are silently skipped.

**Incorrect (one failing callback cancels the rest):**

```python
with transaction.atomic():
    order.save()
    transaction.on_commit(partial(send_receipt, order.pk))
    transaction.on_commit(partial(invalidate_order_cache, order.pk))
```

**What happens:** if `send_receipt` raises, the cache keeps stale data and the client
sees an error page for an order that was placed.

**Correct (each callback is isolated):**

```python
with transaction.atomic():
    order.save()
    transaction.on_commit(partial(send_receipt, order.pk), robust=True)
    transaction.on_commit(partial(invalidate_order_cache, order.pk), robust=True)
```

With `robust=True`, Django catches the exception, logs it with its traceback (logger
`django.db.backends.base`) and moves on to the next callback.

**When not to apply:** a robust callback that fails is only logged; nothing retries it.
For work that must happen, enqueue a task instead (see
`tx-enqueue-in-transaction-db-queue`). Keep non-robust callbacks when a failure must stop
the request and surface to the caller.

**How to detect:** look for several `on_commit()` registrations in the same flow and for
callbacks that call external services. Make sure the `django.db.backends.base` logger
reaches your error tracker, or robust failures go unnoticed.

Reference: [transaction.on_commit()](https://docs.djangoproject.com/en/stable/topics/db/transactions/#django.db.transaction.on_commit)
