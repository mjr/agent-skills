---
title: Run database tests on the same engine as production
impact: HIGH
risk: correctness
django: ">=4.2"
database: any
tags: testing, sqlite, postgresql, select_for_update, ci
sources:
  - https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-for-update
tests: test_detect.py
---

## Run database tests on the same engine as production

SQLite is fast to set up for tests, but it is not PostgreSQL. On SQLite, Django silently
drops the whole `FOR UPDATE` clause of `select_for_update()`, including `of`, `no_key`,
`skip_locked` and `nowait` (no row locks, no error), and raises `NotSupportedError` for
PostgreSQL features such as `distinct(*fields)`; the `django.contrib.postgres` fields,
indexes and functions do not work there at all. Tests of locking, migrations and query plans on SQLite pass for
nothing.

**Incorrect (test settings that swap the engine):**

```python
# settings/test.py
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
```

**What happens:** `Product.objects.select_for_update()` compiles to a plain `SELECT` on
SQLite, so a test meant to prove two requests cannot both update a row proves nothing,
and PostgreSQL-only queries fail only in production.

**Correct:** run tests against the same database engine and major version as production
(a PostgreSQL container in CI and locally), and keep concurrency, migration and query
tests there. If a fast SQLite suite is kept for unrelated unit tests, mark the database
behavior tests so they never run on it.

**When not to apply:** pure logic tests that do not touch the database do not care.

**How to detect:** test settings that change `ENGINE`; CI pipelines without a database
service; tests using `select_for_update`, `distinct(*fields)` or PostgreSQL functions that
pass in seconds on SQLite.

Reference: [QuerySet.select_for_update()](https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-for-update)
