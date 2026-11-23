---
title: Insert and handle the conflict instead of checking first
impact: CRITICAL
risk: correctness
django: ">=5.2"
database: any
tags: unique, integrityerror, race-condition, savepoint, get_or_create
sources:
  - https://hakibenita.com/django-concurrency
tests: test_concurrency_try_create_not_check.py
---

## Insert and handle the conflict instead of checking first

Checking with `exists()` and then calling `create()` leaves a window in which another
request inserts the same row: both requests run the check before either inserts. Only a
unique constraint in the database closes that window, so let the insert fail and handle
the `IntegrityError`.

**Incorrect (check, then create):**

```python
def create_short_url(key, target_url):
    if ShortUrl.objects.filter(key=key).exists():
        raise KeyTaken(key)
    return ShortUrl.objects.create(key=key, target_url=target_url)
```

**What happens:** two concurrent requests both see `exists() == False`. With a unique
constraint, the second `INSERT` raises an `IntegrityError` the code never handles; without
one, a duplicate is stored silently.

**Correct (try the insert inside a savepoint):**

```python
from django.db import IntegrityError, transaction


def create_short_url(key, target_url):
    try:
        with transaction.atomic():
            return ShortUrl.objects.create(key=key, target_url=target_url)
    except IntegrityError:
        raise KeyTaken(key) from None
```

The inner `atomic()` is required, not decoration. When the caller is already inside a
transaction, a failed statement aborts it in PostgreSQL. The savepoint rolls back only the
failed insert; without it, catching the `IntegrityError` is not enough and every later
query in the outer block raises `TransactionManagementError` ("An error occurred in the
current transaction. You can't execute queries until the end of the 'atomic' block.").

`get_or_create()` and `update_or_create()` already follow this pattern internally, but they
are race-safe only when a unique constraint covers the lookup fields. Without one, two
requests can both miss the `get` and both insert.

**When not to apply:** when several constraints can fail, a bare `except IntegrityError`
hides the one you did not expect (a foreign key, a check constraint). Inspect the
constraint that failed before translating the error:

```python
except IntegrityError as error:
    # PostgreSQL names a unique=True constraint <table>_<column>_key.
    if error.__cause__.diag.constraint_name != 'catalog_shorturl_key_key':
        raise
    raise KeyTaken(key) from None
```

`diag.constraint_name` comes from the PostgreSQL driver (psycopg 2 and 3). Constraints
declared with `UniqueConstraint(name=...)` carry the name you chose, which is another
reason to name them.

**How to detect:** look for `.exists()`, `.filter(...).first()` or `.count()` used as a
guard before `create()` or `save()` on the same lookup, and for `get_or_create()` on fields
without a unique constraint. Look for `except IntegrityError` blocks that keep using the
connection without an inner `atomic()`.

Reference: [Handling Concurrency Without Locks](https://hakibenita.com/django-concurrency)
