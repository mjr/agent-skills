---
title: Run on_commit callbacks in tests explicitly
impact: HIGH
risk: correctness
django: ">=4.2"
database: any
tags: testing, on_commit, captureOnCommitCallbacks, testcase
sources:
  - https://hakibenita.com/django-nested-transaction
tests: test_detect.py
---

## Run on_commit callbacks in tests explicitly

`TestCase` (and pytest-django's default `django_db`) wraps each test in a transaction
that is rolled back, never committed. `on_commit()` callbacks therefore never run: a test
of code that correctly defers its email or task passes without the email or task ever
being produced, and a broken callback goes unnoticed.

**Incorrect (asserts nothing about the deferred effect, or asserts it wrongly):**

```python
def test_pay_sends_receipt(self):
    pay(self.payment)
    self.assertEqual(len(mail.outbox), 0)  # Passes for the wrong reason.
```

**Correct (execute the captured callbacks):**

```python
def test_pay_sends_receipt(self):
    with self.captureOnCommitCallbacks(execute=True) as callbacks:
        pay(self.payment)
    self.assertEqual(len(callbacks), 1)
    self.assertEqual(len(mail.outbox), 1)
```

With pytest-django, use the `django_capture_on_commit_callbacks` fixture the same way.
`TransactionTestCase` (`django_db(transaction=True)`) commits for real and runs the
callbacks, at the cost of slower tests.

**When not to apply:** tasks enqueued inside the transaction (see
`tx-enqueue-in-transaction-db-queue`) do not use `on_commit`; test those by inspecting the
queue or running the task.

**How to detect:** tests of code that calls `transaction.on_commit()` (directly or in
signal receivers) without `captureOnCommitCallbacks`.

Reference: [One Database Transaction Too Many: Testing](https://hakibenita.com/django-nested-transaction)
