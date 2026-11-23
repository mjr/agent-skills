---
title: Do not rely on save signals for bulk operations
impact: HIGH
risk: correctness
django: ">=4.2"
database: any
tags: signals, bulk_create, bulk_update, update, delete, post_save
sources:
  - https://docs.djangoproject.com/en/stable/ref/models/querysets/#bulk-create
tests: test_signals.py
---

## Do not rely on save signals for bulk operations

`bulk_create()`, `bulk_update()` and `QuerySet.update()` write directly to the database:
they do not call `save()` and send no `pre_save` or `post_save`. Any receiver, model
`save()` override or library that hooks into saving (audit history, search indexing,
cache invalidation) is silently skipped. `QuerySet.delete()` is the exception: it does
send `pre_delete` and `post_delete` for every row, which also makes it load every row
first when receivers are connected.

**Incorrect (the post_save receiver never runs):**

```python
Payment.objects.filter(status='pending', created__lt=cutoff).update(status='expired')
# The receiver that notifies clients about expired payments is skipped.
```

**Correct (choose explicitly):**

```python
expired = list(Payment.objects.filter(status='pending', created__lt=cutoff).values_list('pk', flat=True))
Payment.objects.filter(pk__in=expired).update(status='expired')
for payment_id in expired:  # The work the receiver would have done, done on purpose.
    payment_expired.send_robust(sender=None, payment_id=payment_id)
```

or iterate and `save()` each object when the per-row behavior matters more than speed.

**When not to apply:** bulk operations are the right tool for large data changes; the
point is to decide what happens to the side effects, not to avoid them. For deletes of
many rows with receivers connected, expect one query to load the rows plus the deletes.

**How to detect:** `bulk_create`, `bulk_update` and `.update(` on models that have
`pre_save` or `post_save` receivers, custom `save()` methods or history tracking.

Reference: [QuerySet.bulk_create()](https://docs.djangoproject.com/en/stable/ref/models/querysets/#bulk-create)
