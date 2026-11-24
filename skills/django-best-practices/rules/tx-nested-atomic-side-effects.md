---
title: Leaving your own atomic() block does not mean the data is committed
impact: CRITICAL
risk: correctness
django: ">=5.2"
database: any
tags: atomic, savepoint, nested-transaction, on_commit, atomic_requests
sources:
  - https://hakibenita.com/django-nested-transaction
tests: test_tx_side_effects.py
---

## Leaving your own atomic() block does not mean the data is committed

A function that writes inside `atomic()` and sends a notification after the block looks
safe on its own. When a caller wraps it in another `atomic()` (a bulk operation, a view
under `ATOMIC_REQUESTS`, a test), the inner block becomes a savepoint: exiting it commits
nothing, and the outer block can still roll everything back after the notification went
out.

**Incorrect (assumes exiting the block committed):**

```python
def pay(payment):
    with transaction.atomic():
        payment.status = 'paid'
        payment.save(update_fields=['status'])
    notify_paid(payment.pk)  # "Safe": the transaction is over. Unless it is not.


def pay_all(payments):
    with transaction.atomic():
        for payment in payments:
            pay(payment)
        reconcile(payments)  # Raises: every payment is rolled back, every notice sent.
```

**What happens:** `pay()` alone sends the notice after a real commit. Called from
`pay_all()`, all notices are sent while the outer transaction is open, and none of the
payments survive the failure in `reconcile()`.

**Correct (let the database decide when the commit happened):**

```python
def pay(payment):
    with transaction.atomic():
        payment.status = 'paid'
        payment.save(update_fields=['status'])
        transaction.on_commit(lambda pk=payment.pk: notify_paid(pk))
```

`on_commit()` callbacks wait for the outermost commit, whatever the nesting.

When a function must run in its own committed transaction (it calls an external system
that needs the data to be visible), forbid nesting with `atomic(durable=True)`; see
`tx-durable-entry-points`.

**When not to apply:** nothing; even code that is never nested today can be wrapped by
`ATOMIC_REQUESTS`, a management command or a test tomorrow. Checking
`connection.in_atomic_block` at runtime works but spreads the concern; prefer
`on_commit()` or `durable=True`.

**How to detect:** look for code after a `with transaction.atomic():` block that sends
notifications, calls APIs or enqueues work to an external broker. Check whether the
project sets `ATOMIC_REQUESTS = True`: then every view body runs inside a transaction.

Reference: [One Database Transaction Too Many](https://hakibenita.com/django-nested-transaction)
