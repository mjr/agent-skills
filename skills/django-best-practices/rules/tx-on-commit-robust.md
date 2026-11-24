---
title: Use on_commit(robust=True) for best-effort callbacks, never with partial before 6.1
impact: MEDIUM
risk: correctness
django: ">=5.2"
database: any
tags: on_commit, robust, callbacks, errors, partial, qualname
sources:
  - https://docs.djangoproject.com/en/stable/topics/db/transactions/#django.db.transaction.on_commit
tests: test_tx_enqueue_in_transaction.py
---

## Use on_commit(robust=True) for best-effort callbacks, never with partial before 6.1

Callbacks registered with `on_commit()` run in order after the commit. When one raises,
the remaining callbacks never run, and the exception reaches the caller even though the
data is already committed: a view returns a 500 for an operation that succeeded, and
later callbacks (a second email, a cache invalidation, an enqueue) are silently skipped.

**Incorrect (one failing callback cancels the rest):**

```python
with transaction.atomic():
    order.save()
    transaction.on_commit(lambda pk=order.pk: send_receipt(pk))
    transaction.on_commit(lambda pk=order.pk: invalidate_order_cache(pk))
```

**What happens:** if `send_receipt` raises, the cache keeps stale data and the client
sees an error page for an order that was placed.

**Correct (each callback is isolated):**

```python
with transaction.atomic():
    order.save()
    transaction.on_commit(lambda pk=order.pk: send_receipt(pk), robust=True)
    transaction.on_commit(lambda pk=order.pk: invalidate_order_cache(pk), robust=True)
```

With `robust=True`, Django catches the exception, logs it with its traceback (logger
`django.db.backends.base`) and moves on to the next callback.

**Do not pass a `functools.partial` with `robust=True` on Django 5.2 and 6.0.** Django
builds the log message with `func.__qualname__`, which a `partial` does not have. When
the callback fails, an `AttributeError` escapes instead of being logged: the data is
committed, the caller still gets a 500, and the later callbacks do not run, which is
exactly what `robust=True` was meant to prevent. `captureOnCommitCallbacks(execute=True)`
has the same bug, so a test that expects the failure to be logged errors. Django 6.1
fixed both. Until then, bind the arguments with a default-argument lambda (as above) or
a named function; both have a `__qualname__`.

**When not to apply:** a robust callback that fails is only logged; nothing retries it.
For work that must happen, enqueue a task instead (see
`tx-enqueue-in-transaction-db-queue`). Keep non-robust callbacks when a failure must stop
the request and surface to the caller.

**How to detect:** look for several `on_commit()` registrations in the same flow and for
callbacks that call external services. On Django 5.2 and 6.0, search for
`on_commit(partial(` combined with `robust=True`. Make sure the
`django.db.backends.base` logger reaches your error tracker, or robust failures go
unnoticed.

Reference: [transaction.on_commit()](https://docs.djangoproject.com/en/stable/topics/db/transactions/#django.db.transaction.on_commit)
