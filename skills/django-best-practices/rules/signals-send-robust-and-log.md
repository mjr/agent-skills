---
title: Send custom signals with send_robust and watch its errors
impact: HIGH
risk: correctness
django: ">=4.2"
database: any
tags: signals, send_robust, errors, decoupling, logging
sources:
  - https://hakibenita.com/django-reliable-signals
tests: test_signals.py
---

## Send custom signals with send_robust and watch its errors

Signals exist so the sender does not depend on its receivers. `send()` breaks that: an
exception in any receiver propagates to the sender, aborts the operation that sent the
signal and skips the receivers registered after it. A bug in an analytics receiver then
fails a payment.

**Incorrect (a receiver's failure becomes the sender's failure):**

```python
payment_completed.send(sender=None, payment_id=payment.pk)
```

**Correct (each receiver is isolated):**

```python
for receiver, response in payment_completed.send_robust(sender=None, payment_id=payment.pk):
    if isinstance(response, Exception):
        ...  # Already logged by Django; add metrics or alerting here if needed.
```

`send_robust()` catches each receiver's `Exception`, keeps calling the others and returns
`(receiver, exception)` pairs. Django also logs each failure with its traceback on the
`django.dispatch` logger, so make sure that logger reaches your error tracker; otherwise
receiver failures are invisible.

**When not to apply:** Django's built-in model signals (`post_save`, `pre_delete`) are
sent with `send()`, and their receivers' errors do abort the save; see
`signals-run-in-sender-transaction`. Use `send()` for your own signals only when a
receiver failing must abort the operation, which usually means it should not be a signal.

**How to detect:** `.send(` calls on custom `Signal()` instances; logging configurations
that do not route `django.dispatch` errors anywhere.

Reference: [Reliable Django Signals: Robust Django Signals](https://hakibenita.com/django-reliable-signals)
