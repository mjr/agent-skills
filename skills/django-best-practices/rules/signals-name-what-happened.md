---
title: Name signals after what happened, not what should happen next
impact: LOW-MEDIUM
risk: correctness
django: ">=4.2"
database: any
tags: signals, naming, decoupling, design
sources:
  - https://hakibenita.com/django-reliable-signals
tests: "none: naming and module design guidance, nothing to execute"
---

## Name signals after what happened, not what should happen next

A signal is how a low-level module announces an event without knowing who listens. A
name that describes the intended reaction (`complete_order`, `send_welcome_email`) ties
the sender to one receiver, invites senders to depend on that receiver having run, and
reads wrong as soon as a second receiver appears.

**Incorrect (the payment module knows about orders):**

```python
# payment/signals.py
complete_order = Signal()
```

**Correct (the event, in the past tense):**

```python
# payment/signals.py
payment_completed = Signal()  # Sent with payment_id, after the commit.
```

Each receiver decides what the event means for it: the order module completes the
order, the analytics module counts it.

Document, next to the signal, which keyword arguments it sends and when (inside or after
the transaction); receivers depend on both.

**When not to apply:** commands to a specific module are not signals; call that
module's function directly.

**How to detect:** signal names that are verbs in the imperative, or that name another
module's model.

Reference: [Reliable Django Signals: Django Signals](https://hakibenita.com/django-reliable-signals)
