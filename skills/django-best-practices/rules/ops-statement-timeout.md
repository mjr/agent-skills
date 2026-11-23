---
title: Bound query and idle-transaction time on every connection
impact: HIGH
risk: availability
django: ">=5.2"
database: postgresql
tags: statement_timeout, idle_in_transaction_session_timeout, options, pgbouncer
sources:
  - https://hakibenita.com/9-django-tips-for-working-with-databases
  - https://www.postgresql.org/docs/current/runtime-config-client.html
tests: test_ops.py
---

## Bound query and idle-transaction time on every connection

Without limits, one bad query (a missing index, an unbounded report) runs for minutes,
holds a connection and locks, and the requests behind it pile up until the application
stops answering. A transaction left open by buggy code (a request that crashed between
`BEGIN` and `COMMIT` in a long-lived connection, a shell session) holds its locks
forever. PostgreSQL can cancel both.

**Incorrect (no limits):**

```python
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', ...}}
```

**Correct (limits set when the connection opens):**

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # ...
        'OPTIONS': {
            'options': '-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000',
        },
    },
}
```

A cancelled query raises `OperationalError` ("canceling statement due to statement
timeout"). An idle transaction past its limit has its session terminated; the next query
on that connection raises `InternalError` ("terminating connection due to
idle-in-transaction timeout").

Use different values per process type when they differ: short for web workers, longer
for background workers and reports (read them from the environment). For one known slow
operation, raise the limit for its transaction only:

```python
with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '5min'")
    run_monthly_report()
```

**When not to apply:** behind PgBouncer, whether the startup `options` parameter reaches
the server depends on its version and configuration (it may be rejected or ignored), and
in transaction pooling mode session settings do not stick; set the limits per role
instead (`ALTER ROLE app_web SET statement_timeout = '30s'`). Migrations may legitimately need longer limits; see
`migration-lock-timeout`.

**How to detect:** settings without `OPTIONS` timeouts and database roles without
defaults (`SELECT rolname, rolconfig FROM pg_roles`); `pg_stat_activity` entries with
old `query_start` or `state = 'idle in transaction'`.

Reference: [9 Django Tips for Working with Databases](https://hakibenita.com/9-django-tips-for-working-with-databases)
