---
title: Connect receivers to a sender and return early when the event is not theirs
impact: MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: signals, post_save, sender, performance
sources:
  - https://hakibenita.com/django-reliable-signals
  - https://hakibenita.com/django-nested-transaction
tests: test_signals.py
---

## Connect receivers to a sender and return early when the event is not theirs

Every receiver runs synchronously on every send. A `post_save` receiver connected
without `sender` runs for every save of every model in the project, including sessions,
admin log entries and history rows. A receiver that queries before deciding it has
nothing to do adds a query to every one of those saves.

**Incorrect (runs and queries for every save in the system):**

```python
@receiver(post_save, dispatch_uid='orders.on_payment_saved')
def on_payment_saved(sender, instance, **kwargs):
    order = Order.objects.filter(payment_id=instance.pk).first()
    if order is None:
        return
    ...
```

**Correct (filtered by sender, cheap checks first):**

```python
@receiver(post_save, sender=Payment, dispatch_uid='orders.on_payment_saved')
def on_payment_saved(sender, instance, created, update_fields=None, **kwargs):
    if created or instance.status != 'paid':
        return
    if update_fields is not None and 'status' not in update_fields:
        return
    try:
        order = Order.objects.get(payment_id=instance.pk)
    except Order.DoesNotExist:
        return  # Another module's payment; not ours.
    ...
```

For custom signals shared by several modules, receivers must expect events that are not
for them and return without failing.

**When not to apply:** receivers that must see every model (generic auditing) cannot
filter by sender, so they must be cheap and avoid queries.

**How to detect:** `post_save`, `pre_save`, `post_delete` and `m2m_changed` receivers
without `sender=`; receivers whose first statement is a query. Count queries around a
save of an unrelated model in a test.

Reference: [Reliable Django Signals](https://hakibenita.com/django-reliable-signals)
