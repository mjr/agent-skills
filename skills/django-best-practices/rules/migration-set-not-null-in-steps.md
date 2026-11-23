---
title: Make a populated column NOT NULL in steps
impact: HIGH
risk: availability
django: ">=4.2"
database: postgresql
tags: not-null, check-constraint, not-valid, backfill, alterfield
sources:
  - https://www.postgresql.org/docs/current/sql-altertable.html
tests: test_migration_set_not_null.py
---

## Make a populated column NOT NULL in steps

Changing a field from `null=True` to `null=False` generates `ALTER COLUMN ... SET NOT
NULL`, which scans every row to prove there are no nulls while holding an
`ACCESS EXCLUSIVE` lock: no reads or writes on the table until the scan finishes. On
PostgreSQL 12 and later, a validated `CHECK (col IS NOT NULL)` constraint lets it skip the
scan, and that constraint can be validated without blocking writes.

**Incorrect (one AlterField on a large table):**

```python
migrations.AlterField('order', 'channel', models.CharField(max_length=20))  # was null=True
```

**Correct (three steps):**

```python
# 1. Backfill existing nulls (data migration or batched command), and deploy code that
#    always writes the column.

# 2. Add a NOT VALID check (instant), then validate it (scans, but allows writes).
migrations.RunSQL(
    'ALTER TABLE orders_order ADD CONSTRAINT order_channel_not_null '
    'CHECK (channel IS NOT NULL) NOT VALID',
    'ALTER TABLE orders_order DROP CONSTRAINT order_channel_not_null',
)
migrations.RunSQL(
    'ALTER TABLE orders_order VALIDATE CONSTRAINT order_channel_not_null',
    migrations.RunSQL.noop,
)

# 3. Set NOT NULL (now only a catalog check) and drop the helper constraint.
migrations.SeparateDatabaseAndState(
    state_operations=[migrations.AlterField('order', 'channel', models.CharField(max_length=20))],
    database_operations=[
        migrations.RunSQL(
            'ALTER TABLE orders_order ALTER COLUMN channel SET NOT NULL',
            'ALTER TABLE orders_order ALTER COLUMN channel DROP NOT NULL',
        ),
        migrations.RunSQL(
            'ALTER TABLE orders_order DROP CONSTRAINT order_channel_not_null',
            'ALTER TABLE orders_order ADD CONSTRAINT order_channel_not_null '
            'CHECK (channel IS NOT NULL) NOT VALID',
        ),
    ],
)
```

Put each step in its own migration (and the validation in its own deploy if the table
is very large), so a slow validation never shares a transaction with the brief
exclusive lock of step 3.

**When not to apply:** on small tables the plain `AlterField` is fine. On PostgreSQL 11
and older, `SET NOT NULL` always scans.

**How to detect:** `AlterField` removing `null=True` on large tables; `SET NOT NULL` in
`sqlmigrate` output. The server logs "existing constraints on column ... are sufficient
to prove that it does not contain nulls" at `DEBUG1` when the shortcut is taken.

Reference: [PostgreSQL ALTER TABLE: SET NOT NULL](https://www.postgresql.org/docs/current/sql-altertable.html)
