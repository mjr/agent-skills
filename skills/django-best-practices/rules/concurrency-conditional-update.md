---
title: Put the check in the UPDATE instead of reading first
impact: CRITICAL
risk: correctness
django: ">=5.2"
database: any
tags: conditional-update, f-expression, select_for_update, balance, stock
sources:
  - https://hakibenita.com/django-concurrency
tests: test_concurrency_conditional_update.py
---

## Put the check in the UPDATE instead of reading first

"Withdraw only if the balance is enough" and "sell only if there is stock" are decisions
on the current value. Reading the row, checking in Python and writing back lets two
requests pass the same check. Expressing the condition in the `WHERE` clause makes the
database check and write in one step, with no lock held while Python runs.

**Incorrect (the check runs on a value that may already be stale):**

```python
wallet = Wallet.objects.get(pk=pk)
if wallet.balance < amount:
    raise InsufficientFunds()
wallet.balance -= amount
wallet.save(update_fields=['balance'])
```

**What happens:** two withdrawals of 80 from a balance of 100 both read 100, both pass the
check and the account pays out 160.

**Correct (the condition and the write in one statement):**

```python
updated = Wallet.objects.filter(pk=pk, balance__gte=amount).update(
    balance=F('balance') - amount,
)
if not updated:
    raise InsufficientFunds()
```

A concurrent `UPDATE` of the same row waits for the first to commit, then re-evaluates
its `WHERE` clause against the new value; the second withdrawal matches no row and
`update()` returns 0.

**When the condition cannot be written as a filter** (it needs several rows, an external
call or complex Python logic), lock the row and keep the transaction short:

```python
with transaction.atomic():
    wallet = Wallet.objects.select_for_update(of=('self',), no_key=True).get(pk=pk)
    if not can_withdraw(wallet, amount):
        raise InsufficientFunds()
    wallet.balance = F('balance') - amount
    wallet.save(update_fields=['balance'])
```

The lock is held while Python decides, so every other writer of that row waits. Never
make network calls while holding it.

**When not to apply:** if the value is only ever read (a display), no protection is
needed. If any change is acceptable regardless of the current value, a plain `F()` update
is enough (`concurrency-f-expressions`).

**How to detect:** look for `if obj.<field> <, >, >= ...` followed by a write of the same
field, in code without `select_for_update()`. In a test, run the same operation from two
connections and assert the invariant (no negative balance, no oversold stock).

Reference: [Handling Concurrency Without Locks](https://hakibenita.com/django-concurrency)
