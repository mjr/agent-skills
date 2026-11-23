---
title: Use UPDATE ... RETURNING when you need the new value in one round trip
impact: LOW-MEDIUM
risk: performance
django: ">=4.2"
database: postgresql
tags: returning, raw-sql, counter, round-trip
sources:
  - https://hakibenita.com/django-concurrency
tests: test_concurrency_update_returning.py
---

## Use UPDATE ... RETURNING when you need the new value in one round trip

Incrementing safely with `F()` and then reading the result takes extra queries: a read to
get the instance, the update, and (before Django 6.0) a refresh. On a hot path, such as
resolving a short URL on every visit, PostgreSQL's `UPDATE ... RETURNING` does all of it
in one statement.

**Incorrect (three queries on Django 5.2, two on 6.0+):**

```python
url = ShortUrl.objects.get(key=key)
url.hits = F('hits') + 1
url.save(update_fields=['hits'])
url.refresh_from_db(fields=['hits'])  # Not needed on 6.0+, which reads it back.
```

**Correct (one statement, the updated row comes back):**

```python
from django.db import connection


def resolve(key):
    table = connection.ops.quote_name(ShortUrl._meta.db_table)
    rows = list(
        ShortUrl.objects.raw(
            f'UPDATE {table} SET hits = hits + 1 WHERE key = %s RETURNING *',
            [key],
        )
    )
    if not rows:
        raise ShortUrl.DoesNotExist(key)
    return rows[0]
```

Values always go through parameters (`%s`). Identifiers cannot be parameters, so quote
them with `connection.ops.quote_name()` and build them only from model metadata, never
from user input.

**When not to apply:** this is raw SQL: no model validation, no signals, no
`django-simple-history`-style hooks, and the column names are written by hand. Use it
only on paths where the saved round trip matters. On Django 6.0+, if the instance is
already loaded for other reasons, `save()` with an `F()` expression already returns the
new value.

**How to detect:** look for `get()` + `F()` + `save()` + `refresh_from_db()` sequences on
endpoints that run on every request.

Reference: [Handling Concurrency Without Locks](https://hakibenita.com/django-concurrency)
