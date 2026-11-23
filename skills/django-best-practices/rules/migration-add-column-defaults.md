---
title: Know how a new column's default is applied before adding it to a big table
impact: HIGH
risk: availability
django: ">=5.0"
database: postgresql
tags: addfield, default, db_default, rewrite, uuid
sources:
  - https://docs.djangoproject.com/en/stable/howto/writing-migrations/#migrations-that-add-unique-fields
  - https://www.postgresql.org/docs/current/sql-altertable.html
tests: test_migration_add_column_defaults.py
---

## Know how a new column's default is applied before adding it to a big table

On PostgreSQL 11 and later, adding a column with a constant default does not touch the
existing rows; it is instant. Three details decide whether a new column stays that cheap
and behaves as expected:

- **A Python `default` is evaluated once.** Django computes it in Python and uses that
  single value for every existing row, then drops the database default. With
  `default=uuid.uuid4` every existing row gets the same UUID, and a later `unique=True`
  fails.
- **The column has no database default afterwards.** Inserts from code that does not
  know the column (other services, raw SQL, the previous release still running during
  the deploy) fail on a `NOT NULL` column.
- **A volatile `db_default` rewrites the table.** `db_default=RandomUUID()` (or any
  `gen_random_uuid()`, `random()`, `clock_timestamp()`) is computed per row by rewriting
  the whole table under an `ACCESS EXCLUSIVE` lock. Non-volatile expressions such as
  `db_default=Now()` stay instant (all rows get the same value).

**Incorrect (looks like a per-row value, is one value):**

```python
migrations.AddField('order', 'public_id', models.UUIDField(default=uuid.uuid4, unique=True))
```

**What happens:** the migration fails on the unique index, or, without `unique=True`,
every existing order shares one `public_id`.

**Correct (add nullable, fill per row in batches, then constrain):**

```python
# 1. Add the column as nullable: instant.
migrations.AddField('order', 'public_id', models.UUIDField(null=True))

# 2. Backfill in batches, in a separate migration or a management command.
def backfill(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    while ids := list(Order.objects.filter(public_id=None).values_list('pk', flat=True)[:1000]):
        for pk in ids:
            Order.objects.filter(pk=pk).update(public_id=uuid.uuid4())

# 3. Add the unique index concurrently, then make it NOT NULL
#    (see migration-concurrent-indexes and migration-set-not-null-in-steps).
```

For a constant that other writers must also get, use `db_default` (Django 5.0+), which
keeps the default in the database: `models.BooleanField(db_default=False)`.

**When not to apply:** on new or small tables none of this matters; `default=` with a
constant is fine anywhere.

**How to detect:** `AddField` with a callable `default` (`uuid4`, `timezone.now`,
functions) on existing tables; `db_default` with volatile functions; NOT NULL columns
added with a Python-only default to tables that other systems write.

Reference: [Migrations that add unique fields](https://docs.djangoproject.com/en/stable/howto/writing-migrations/#migrations-that-add-unique-fields)
