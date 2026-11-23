---
title: Add foreign keys to populated columns as NOT VALID, then validate
impact: MEDIUM
risk: availability
django: ">=5.2"
database: postgresql
tags: foreign-key, not-valid, validate-constraint, locks
sources:
  - https://www.postgresql.org/docs/current/sql-altertable.html
tests: test_migration_fk_not_valid.py
---

## Add foreign keys to populated columns as NOT VALID, then validate

Turning an existing integer column into a `ForeignKey` (or adding a foreign key to a
column that already has data) makes PostgreSQL check every row against the referenced
table while holding a `SHARE ROW EXCLUSIVE` lock on both tables. Inserts and updates on
both are blocked for the whole check. Django always generates the blocking form.

**Incorrect (the generated AlterField from IntegerField to ForeignKey):**

```sql
ALTER TABLE "orders_item" ADD CONSTRAINT "orders_item_owner_id_fk"
    FOREIGN KEY ("owner_id") REFERENCES "accounts_owner" ("id") DEFERRABLE INITIALLY DEFERRED;
```

**Correct (add without checking existing rows, check them separately):**

```python
migrations.SeparateDatabaseAndState(
    state_operations=[migrations.AlterField('item', 'owner', models.ForeignKey(...))],
    database_operations=[
        migrations.RunSQL(
            'ALTER TABLE orders_item ADD CONSTRAINT orders_item_owner_id_fk '
            'FOREIGN KEY (owner_id) REFERENCES accounts_owner (id) '
            'DEFERRABLE INITIALLY DEFERRED NOT VALID',
            'ALTER TABLE orders_item DROP CONSTRAINT orders_item_owner_id_fk',
        ),
    ],
)

# Next migration:
migrations.RunSQL(
    'ALTER TABLE orders_item VALIDATE CONSTRAINT orders_item_owner_id_fk',
    migrations.RunSQL.noop,
)
```

`NOT VALID` takes the lock only briefly, and the constraint is enforced for new and
updated rows right away. `VALIDATE CONSTRAINT` then checks the old rows with a lock that
allows writes to both tables. Remember the implicit index: create it concurrently too
(see `migration-concurrent-indexes`).

**When not to apply:** adding a new nullable `ForeignKey` column is fine as generated:
the column is empty, so the check is instant. The same applies to small tables.

**How to detect:** `ADD CONSTRAINT ... FOREIGN KEY` without `NOT VALID` on existing
tables in `sqlmigrate` output; `scripts/check_migration_sql.py` reports it.

Reference: [PostgreSQL ALTER TABLE: NOT VALID](https://www.postgresql.org/docs/current/sql-altertable.html)
