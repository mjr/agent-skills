---
title: Define signals in the sender's module and connect module-level receivers in ready()
impact: MEDIUM
risk: correctness
django: ">=4.2"
database: any
tags: signals, circular-import, apps-ready, weak-references, receivers
sources:
  - https://hakibenita.com/django-reliable-signals
tests: test_signals.py
---

## Define signals in the sender's module and connect module-level receivers in ready()

When a low-level module (payments) needs to tell a high-level one (orders) that
something happened, importing the high-level module from the low-level one creates a
circular import and a dependency in the wrong direction. A signal defined in the
low-level module reverses it: orders imports payments and subscribes. Two details make
receivers silently stop working: signals hold weak references to receivers by default,
and receivers must be importable functions.

**Incorrect (the receiver can disappear):**

```python
class OrderService:
    def __init__(self):
        payment_completed.connect(self.on_payment_completed)  # Bound method, weak ref.

    def on_payment_completed(self, payment_id, **kwargs):
        ...


def setup():
    def receiver(payment_id, **kwargs):  # Local function, weak ref.
        ...

    payment_completed.connect(receiver)
```

**What happens:** once the `OrderService` instance or the local function is garbage
collected, the weak reference dies and the signal stops calling it, with no error.

**Correct (module-level function, connected once at startup):**

```python
# payment/signals.py
payment_completed = Signal()

# order/receivers.py
@receiver(payment_completed, dispatch_uid='order.on_payment_completed')
def on_payment_completed(payment_id, **kwargs):
    Order.complete_for_payment(payment_id)

# order/apps.py
class OrderConfig(AppConfig):
    name = 'order'

    def ready(self):
        from . import receivers  # noqa: F401
```

Receivers cannot be instance or class methods if they are meant to live as long as the
process; keep a namespaced `@staticmethod` on the model or a module function. Use
`weak=False` only for receivers you deliberately create at runtime.

**When not to apply:** if the low-level module really needs the result of the
high-level one, the dependency is real; a signal would hide it rather than remove it.

**How to detect:** `connect(self.` calls, receivers defined inside functions without
`weak=False`, receiver modules that are never imported from `ready()`, and imports from
a higher-level app inside a lower-level one.

Reference: [Reliable Django Signals: Decoupling Modules](https://hakibenita.com/django-reliable-signals)
