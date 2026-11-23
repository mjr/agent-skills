---
title: Mark transactions that must commit on exit with durable=True
impact: MEDIUM
risk: correctness
django: ">=4.2"
database: any
tags: atomic, durable, entry-point, nested-transaction
sources:
  - https://hakibenita.com/django-nested-transaction
tests: test_tx_side_effects.py
---

## Mark transactions that must commit on exit with durable=True

Some operations are only correct if their data is committed when they return: capturing
a payment before calling the provider, finishing a step that a separate process reads
right after. Nothing stops a caller from wrapping them in another transaction, which turns
the commit into a savepoint. `atomic(durable=True)` raises instead of silently nesting.

**Incorrect (works until someone nests it):**

```python
def capture_payment(payment_id):
    with transaction.atomic():
        payment = Payment.objects.select_for_update(of=('self',)).get(pk=payment_id)
        payment.status = 'capturing'
        payment.save(update_fields=['status'])
    provider.capture(payment_id)  # The provider calls back and must see 'capturing'.
```

**Correct (nesting fails loudly):**

```python
def capture_payment(payment_id):
    with transaction.atomic(durable=True):
        payment = Payment.objects.select_for_update(of=('self',)).get(pk=payment_id)
        payment.status = 'capturing'
        payment.save(update_fields=['status'])
    provider.capture(payment_id)
```

Called inside another `atomic()`, the durable block raises `RuntimeError` ("A durable
atomic block cannot be nested within another atomic block."). Django's `TestCase`
transactions are exempt, so durable blocks still work in normal tests.

**When not to apply:** a durable function cannot be composed into a larger transaction,
so a bulk variant has to be written separately. When the only concern is "do this after
the commit", `on_commit()` is the lighter fix and keeps the function composable.

**How to detect:** look for functions whose correctness depends on the commit having
happened before they return: external calls right after an `atomic()` block, handoffs to
other processes, code that reads its own writes through another connection.

Reference: [transaction.atomic(durable=True)](https://docs.djangoproject.com/en/stable/topics/db/transactions/#django.db.transaction.atomic)
