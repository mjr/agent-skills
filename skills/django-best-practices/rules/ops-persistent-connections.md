---
title: Reuse database connections with CONN_MAX_AGE or the connection pool
impact: MEDIUM
risk: performance
django: ">=5.1"
database: postgresql
tags: conn_max_age, conn_health_checks, pool, pgbouncer, connections
sources:
  - https://docs.djangoproject.com/en/stable/ref/databases/#persistent-connections
  - https://docs.djangoproject.com/en/stable/ref/databases/#connection-pool
tests: test_ops.py
---

## Reuse database connections with CONN_MAX_AGE or the connection pool

By default (`CONN_MAX_AGE = 0`) Django opens a new database connection for every request
and closes it at the end. On PostgreSQL each new connection forks a server process and
authenticates, often costing more than the queries of a simple request.

**Incorrect (the default):**

```python
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', ...}}
```

**Correct (persistent connections):**

```python
DATABASES = {
    'default': {
        # ...
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,  # Replace connections that died while idle.
    },
}
```

or, on Django 5.1+ with psycopg 3, the built-in pool (install `psycopg[pool]`):

```python
DATABASES = {
    'default': {
        # ...
        'OPTIONS': {'pool': {'min_size': 2, 'max_size': 10}},
    },
}
```

The pool cannot be combined with `CONN_MAX_AGE` other than 0; Django raises
`ImproperlyConfigured`.

Size the total: every process (each gunicorn worker, each task worker) holds its own
connections, so `processes * connections per process` must stay below the server's
`max_connections`. When it does not, put PgBouncer in front of the database. In
transaction pooling mode, disable server-side cursors (`DISABLE_SERVER_SIDE_CURSORS`;
see `query-iterator-large-sets`) and session-level settings (see
`ops-statement-timeout`).

**When not to apply:** with PgBouncer in transaction mode handling the pooling, keep
Django's own pool off and `CONN_MAX_AGE` low or 0. Development servers gain little.

**How to detect:** settings without `CONN_MAX_AGE` or `pool`; many short-lived
connections in the PostgreSQL logs (`log_connections`) or a high rate of new backends.

Reference: [Persistent connections](https://docs.djangoproject.com/en/stable/ref/databases/#persistent-connections)
