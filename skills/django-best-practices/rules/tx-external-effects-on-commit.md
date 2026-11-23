---
title: Run effects outside the database only after the commit
impact: CRITICAL
risk: correctness
django: ">=5.2"
database: any
tags: on_commit, email, webhook, cache, rollback
sources:
  - https://hakibenita.com/django-nested-transaction
  - https://hakibenita.com/django-reliable-signals
tests: test_tx_side_effects.py
---

## Run effects outside the database only after the commit

An email, an HTTP call, a push notification or a cache write cannot be rolled back. Sent
inside a transaction, it survives a rollback and reports an event that never happened. It
can also run ahead of the data: a partner that receives your webhook and calls your API
back may not see the rows yet, because other connections only see them after the commit.

**Incorrect (the effect happens before the commit):**

```python
with transaction.atomic():
    payment.status = 'paid'
    payment.save(update_fields=['status'])
    send_receipt(payment.pk)
    ledger.record(payment)  # If this raises, the receipt was still sent.
```

**What happens:** when anything later in the block fails, the payment is rolled back and
the client keeps an email for a payment that does not exist.

**Correct (defer the effect to the commit):**

```python
from functools import partial

with transaction.atomic():
    payment.status = 'paid'
    payment.save(update_fields=['status'])
    transaction.on_commit(partial(send_receipt, payment.pk))
    ledger.record(payment)
```

The callback runs after the outermost transaction commits and is discarded on rollback.
Outside any transaction, `on_commit()` runs the callback immediately. Invalidate caches
the same way: done before the commit, another request can repopulate the cache with the
old data before the new data is visible.

**When not to apply:** `on_commit()` closes the rollback problem but opens another one: if
the process dies between the commit and the callback, the effect is lost (see
`tx-enqueue-in-transaction-db-queue` for effects that must not be lost). Effects that
target the same database (writing another row) belong inside the transaction, not after
it.

**How to detect:** look for `send_mail`, HTTP clients, push or webhook calls, `cache.set`
and `cache.delete` inside `atomic()` blocks, in signal receivers and in model methods that
callers may wrap in a transaction. In `TestCase` tests, `on_commit()` callbacks never run
unless the test uses `captureOnCommitCallbacks(execute=True)`.

Reference: [One Database Transaction Too Many](https://hakibenita.com/django-nested-transaction)
