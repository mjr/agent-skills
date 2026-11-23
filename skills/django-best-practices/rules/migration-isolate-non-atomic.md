---
title: Put non-atomic operations in a migration of their own
impact: HIGH
risk: availability
django: ">=4.2"
database: any
tags: atomic, non-atomic, migration, partial-failure
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_migration_non_atomic.py
---

## Put non-atomic operations in a migration of their own

An atomic migration either applies completely or not at all. A migration with
`atomic = False` applies each operation as it goes: if one fails, the earlier ones stay
applied and the migration is not recorded as applied. Running `migrate` again then
repeats the operations that already ran and fails ("column already exists"), and someone
has to fix the database by hand.

**Incorrect (schema and data changes mixed with a concurrent index):**

```python
class Migration(migrations.Migration):
    atomic = False

    operations = [
        migrations.AddField('order', 'channel', models.CharField(max_length=20, null=True)),
        migrations.RunPython(backfill_channel, migrations.RunPython.noop),
        AddIndexConcurrently('order', models.Index(fields=['channel'], name='order_channel_ix')),
    ]
```

**What happens:** if the backfill fails, the column exists, the migration is unrecorded
and the next `migrate` crashes on `AddField`.

**Correct (atomic work in one migration, concurrent index work in the next):**

```python
# 0042_order_channel.py: atomic (the default)
operations = [
    migrations.AddField('order', 'channel', models.CharField(max_length=20, null=True)),
    migrations.RunPython(backfill_channel, migrations.RunPython.noop),
]

# 0043_order_channel_index.py
class Migration(migrations.Migration):
    atomic = False
    dependencies = [('orders', '0042_order_channel')]
    operations = [
        AddIndexConcurrently('order', models.Index(fields=['channel'], name='order_channel_ix')),
    ]
```

A non-atomic migration should contain only operations that cannot run in a transaction
(concurrent index operations) and, when they belong together, the state operations for
them.

**When not to apply:** a large data backfill is sometimes deliberately non-atomic so it
can commit in batches; then make each batch idempotent so a re-run continues where it
stopped instead of failing.

**How to detect:** `atomic = False` migrations with `AddField`, `AlterField`,
`RunPython` or `RunSQL` statements other than `CONCURRENTLY`; in `sqlmigrate` output, a
migration without `BEGIN;` that contains other statements.
`scripts/check_migration_sql.py` reports both.

Reference: [Django Foreign Keys: Concurrent Index Operations](https://hakibenita.com/django-foreign-keys)
