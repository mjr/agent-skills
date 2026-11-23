---
title: Send primary keys and plain values in signals, not model instances
impact: MEDIUM
risk: correctness
django: ">=5.2"
database: any
tags: signals, arguments, tasks, serialization
sources:
  - https://hakibenita.com/django-reliable-signals
tests: test_signals.py
---

## Send primary keys and plain values in signals, not model instances

An instance passed through a signal is whatever the sender had in memory: possibly
unsaved changes, possibly stale. It also cannot cross a process boundary. The day a
receiver moves to a background task (to make it reliable or to take it off the request),
every receiver that relied on getting an instance has to change, because task queues
only accept JSON-serializable arguments.

**Incorrect:**

```python
payment_completed.send_robust(sender=None, payment=payment)
```

**Correct:**

```python
payment_completed.send_robust(sender=None, payment_id=payment.pk)
```

Receivers load what they need, inside their own transaction and with the locks they
need. If several receivers need the same extra data, send the plain values (`amount`,
`currency`) rather than the instance.

**When not to apply:** Django's built-in model signals send the instance and receivers
of `pre_save` legitimately inspect it; this rule is about custom signals.

**How to detect:** custom signals sent with model instances as keyword arguments;
`enqueue(instance)` or `delay(instance)` calls, which fail with a serialization error.

Reference: [Reliable Django Signals: Limitations](https://hakibenita.com/django-reliable-signals)
