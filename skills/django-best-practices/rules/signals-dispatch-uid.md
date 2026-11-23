---
title: Pass dispatch_uid when a receiver can be connected more than once
impact: MEDIUM
risk: correctness
django: ">=5.2"
database: any
tags: signals, dispatch_uid, duplicate-receivers, apps-ready
sources:
  - https://docs.djangoproject.com/en/stable/topics/signals/#preventing-duplicate-signals
tests: test_signals.py
---

## Pass dispatch_uid when a receiver can be connected more than once

Django identifies a receiver by the function object. Connecting the same module-level
function twice is harmless; connecting a new function object each time is not. That
happens when receivers are defined inside a function that runs more than once (a factory,
an `AppConfig.ready()` called again in tests), or when a module is imported under two
names. Each connection then runs, and the side effect happens twice.

**Incorrect (each call to register() adds another receiver):**

```python
def register_notifications():
    @receiver(payment_completed)
    def notify(payment_id, **kwargs):
        send_receipt(payment_id)
```

**Correct (one registration per id, however many times it runs):**

```python
def register_notifications():
    @receiver(payment_completed, dispatch_uid='payments.send_receipt')
    def notify(payment_id, **kwargs):
        send_receipt(payment_id)
```

Prefer module-level receivers imported once from `AppConfig.ready()`; `dispatch_uid`
makes them safe even if the import path changes. Use a stable, descriptive string (not a
random value generated at import time, which would defeat the purpose).

**When not to apply:** a receiver function defined at module level and connected from
`ready()` is already deduplicated by identity; the uid adds safety, not correctness.

**How to detect:** receivers defined inside functions or methods; `connect()` calls in
code that can run more than once; duplicate emails or tasks that appear only in some
environments.

Reference: [Preventing duplicate signals](https://docs.djangoproject.com/en/stable/topics/signals/#preventing-duplicate-signals)
