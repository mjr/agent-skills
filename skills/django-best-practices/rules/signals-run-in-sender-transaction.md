---
title: Remember that receivers run inside the sender's transaction
impact: HIGH
risk: correctness
django: ">=5.2"
database: any
tags: signals, post_save, transactions, rollback
sources:
  - https://hakibenita.com/django-reliable-signals
tests: test_signals.py
---

## Remember that receivers run inside the sender's transaction

Receivers are called synchronously, in the middle of the sender's code. When the signal
is sent inside a transaction (every `post_save` of a save inside `atomic()`, every view
under `ATOMIC_REQUESTS`), the receivers' database writes join that transaction: they roll
back with it, and their own `atomic()` blocks are only savepoints. Their slow work
lengthens it, and an error in a model signal receiver aborts the save.

**Incorrect (assumes the receiver's audit row is independent):**

```python
@receiver(post_save, sender=Payment, dispatch_uid='audit.payment_saved')
def record_audit(sender, instance, **kwargs):
    AuditEntry.objects.create(action='payment_saved', object_id=instance.pk)
    analytics.track('payment_saved', instance.pk)  # HTTP call inside the transaction.
```

**What happens:** if the caller's transaction rolls back, the audit entry disappears with
it, yet the analytics event was already sent. If `analytics.track` raises, the payment
save fails.

**Correct (database work in the transaction on purpose, the rest after the commit):**

```python
@receiver(post_save, sender=Payment, dispatch_uid='audit.payment_saved')
def record_audit(sender, instance, **kwargs):
    AuditEntry.objects.create(action='payment_saved', object_id=instance.pk)
    transaction.on_commit(lambda pk=instance.pk: analytics.track('payment_saved', pk), robust=True)
```

Writes that must happen together with the sender's belong in the transaction; anything
else is deferred (see `tx-external-effects-on-commit`) or enqueued as a task (see
`tx-enqueue-in-transaction-db-queue`).

**When not to apply:** receivers that only read, and run fast, need nothing special.

**How to detect:** receivers that make network calls, send email or write to other
systems; receivers that wrap their own logic in `atomic()` expecting independence.

Reference: [Reliable Django Signals: Django Signals and Database Transactions](https://hakibenita.com/django-reliable-signals)
