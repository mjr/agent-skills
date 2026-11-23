---
title: Set a lock_timeout for migrations
impact: HIGH
risk: availability
django: ">=4.2"
database: postgresql
tags: lock_timeout, alter-table, lock-queue, migrate
sources:
  - https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-LOCK-TIMEOUT
tests: test_migration_lock_timeout.py
---

## Set a lock_timeout for migrations

Most schema changes need an `ACCESS EXCLUSIVE` lock, even the instant ones (adding a
nullable column takes milliseconds once it has the lock). If any transaction is using
the table (a slow report, an idle-in-transaction connection), the `ALTER TABLE` waits;
and while it waits, every new query on the table queues behind it. A migration that is
merely waiting takes the table offline.

**Incorrect (no limit on the wait):**

```console
$ python manage.py migrate   # waits as long as the oldest transaction on the table
```

**What happens:** a long-running `SELECT` holds `ACCESS SHARE`; the migration's
`ALTER TABLE` queues for `ACCESS EXCLUSIVE`; every later `SELECT`, `INSERT` and `UPDATE`
on that table queues behind the migration until the long query ends.

**Correct (fail fast and retry later):**

Set the timeout for the `migrate` process only, through the connection options, without
touching migration files:

```python
# settings.py
DATABASES['default']['OPTIONS'] = {
    'options': f"-c lock_timeout={os.environ.get('DB_LOCK_TIMEOUT', '0')}",
}
```

```console
$ DB_LOCK_TIMEOUT=5s python manage.py migrate
```

or inside a specific atomic migration, scoped to its transaction:

```python
operations = [
    migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
    migrations.AddField(...),
]
```

When the lock is not obtained in time the statement fails with "canceling statement due
to lock timeout", the migration rolls back, and the application keeps working; retry the
deploy when the table is quieter. Pair it with a `statement_timeout` for operations that
should never run long.

**When not to apply:** concurrent index builds wait for transactions by design and take
a weaker lock; a short `lock_timeout` makes them fail needlessly, so run those
migrations without it. `SET LOCAL` has no effect in non-atomic migrations.

**How to detect:** deploy scripts that run `migrate` without any lock or statement
timeout; `scripts/check_migration_sql.py` notes migrations with `ALTER TABLE` and no
`lock_timeout`. In PostgreSQL, `pg_stat_activity` rows with `wait_event_type = 'Lock'`
during a deploy show the queue forming.

Reference: [PostgreSQL lock_timeout](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-LOCK-TIMEOUT)
