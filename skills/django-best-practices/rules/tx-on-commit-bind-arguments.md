---
title: Bind callback arguments when registering on_commit, not when it runs
impact: MEDIUM
risk: correctness
django: ">=4.2"
database: any
tags: on_commit, lambda, late-binding, partial
sources:
  - https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
tests: test_tx_side_effects.py
---

## Bind callback arguments when registering on_commit, not when it runs

`on_commit()` stores the callable and runs it later. A `lambda` looks variables up when
it runs, not when it is created, so lambdas registered in a loop all see the loop
variable's final value: every callback acts on the last item.

**Incorrect (all callbacks use the last payment):**

```python
with transaction.atomic():
    for payment in payments:
        payment.mark_paid()
        transaction.on_commit(lambda: send_receipt(payment.pk))
```

**What happens:** the last client gets one receipt per payment in the batch, and the
others get none.

**Correct (bind the value at registration):**

```python
from functools import partial

with transaction.atomic():
    for payment in payments:
        payment.mark_paid()
        transaction.on_commit(partial(send_receipt, payment.pk))
```

`partial` evaluates `payment.pk` immediately. A default argument
(`lambda pk=payment.pk: send_receipt(pk)`) works too but is easier to break in review.
Pass primary keys or plain values rather than instances: an instance changed later in the
transaction is seen in its final state by the callback.

**When not to apply:** a lambda with no free variables that change (`lambda:
cache.clear()`) is fine.

**How to detect:** search for `on_commit(lambda` inside `for` loops and comprehensions,
and in receivers that run once per object of a bulk operation.

Reference: [Python FAQ: lambdas defined in a loop](https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result)
