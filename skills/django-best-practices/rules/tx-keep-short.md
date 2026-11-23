---
title: Keep network calls and slow work out of transactions
impact: HIGH
risk: availability
django: ">=5.2"
database: any
tags: atomic, locks, network, atomic_requests, long-transaction
sources:
  - https://hakibenita.com/django-reliable-signals
tests: test_tx_side_effects.py
---

## Keep network calls and slow work out of transactions

Every row a transaction updates stays locked until it commits. A call to a payment
provider, an email server or any API inside the transaction holds those locks for as long
as the remote side takes, and every other request that touches the same rows waits. One
slow partner then slows down unrelated parts of the application.

**Incorrect (the row is locked while waiting for the network):**

```python
with transaction.atomic():
    order.status = 'paid'
    order.save(update_fields=['status'])
    shipping.create_label(order.pk)  # 5 seconds on a bad day.
```

**What happens:** for the whole call, any `UPDATE` of that order (a cancellation, an
admin edit, a webhook) blocks. Connections pile up waiting, and under load the pool runs
out.

**Correct (commit first, then call; or hand the call to a task):**

```python
with transaction.atomic():
    order.status = 'paid'
    order.save(update_fields=['status'])
    create_shipping_label.enqueue(order.pk)  # Or on_commit() for best-effort calls.
```

If the call must happen before the write (you need its result), make it before opening
the transaction and write the result in a short transaction afterwards.

**When not to apply:** calls to the same database are not network side effects; keep
them inside when they must be atomic with the rest. Read-only transactions hold fewer
locks but still pin a connection and block `VACUUM` from cleaning up.

**How to detect:** look for HTTP clients, SDK calls, `send_mail`, file uploads and
`time.sleep` inside `atomic()` blocks and inside signal receivers. With
`ATOMIC_REQUESTS = True`, the whole view is one transaction, so any external call in a
view counts. In PostgreSQL, sessions in state `idle in transaction` in
`pg_stat_activity` show transactions waiting on the application.

Reference: [Reliable Django Signals](https://hakibenita.com/django-reliable-signals)
