---
title: Change a foreign key's index without re-creating the constraint
impact: CRITICAL
risk: availability
django: ">=5.2"
database: postgresql
tags: foreign-key, db_index, separatedatabaseandstate, runsql, concurrently
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_migration_fk_db_index_change.py
---

## Change a foreign key's index without re-creating the constraint

Changing `db_index` on an existing `ForeignKey`, in either direction, generates an
`AlterField` that drops the whole foreign key constraint and adds it back: turning it off
(to drop a redundant index, or to replace it with a partial one) and turning it on (the
index is then also built without `CONCURRENTLY`, blocking writes). Adding the constraint
back locks the table and checks every row against the referenced table. Django 5.2, 6.0
and 6.1 all do this.

**Incorrect (the generated migration):**

```python
operations = [
    migrations.AlterField(
        model_name='product',
        name='category',
        field=models.ForeignKey(db_index=False, on_delete=models.PROTECT, to='catalog.category'),
    ),
]
```

**What happens:**

```sql
ALTER TABLE "catalog_product" DROP CONSTRAINT "catalog_product_category_id_..._fk_...";
DROP INDEX IF EXISTS "catalog_product_category_id_35bf920b";
ALTER TABLE "catalog_product" ADD CONSTRAINT "catalog_product_category_id_..._fk_..."
    FOREIGN KEY ("category_id") REFERENCES "catalog_category" ("id") DEFERRABLE INITIALLY DEFERRED;
```

**Correct (record the state change, run only the index drop):**

```python
class Migration(migrations.Migration):
    atomic = False  # CONCURRENTLY cannot run inside a transaction.

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='product',
                    name='category',
                    field=models.ForeignKey(
                        db_index=False, on_delete=models.PROTECT, to='catalog.category'
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY IF EXISTS "catalog_product_category_id_35bf920b"',
                    reverse_sql=(
                        'CREATE INDEX CONCURRENTLY "catalog_product_category_id_35bf920b" '
                        'ON "catalog_product" ("category_id")'
                    ),
                ),
            ],
        ),
    ]
```

Take the index name and the reverse SQL from `sqlmigrate` of the migration that created
the field. `RemoveIndexConcurrently` cannot do this: it only handles indexes declared in
`Meta.indexes`, not the one a `ForeignKey` creates implicitly. Confirm the state matches
with `makemigrations --check`.

To turn the index on, swap the statements: `CREATE INDEX CONCURRENTLY ...` as `sql` and
`DROP INDEX CONCURRENTLY ...` as `reverse_sql`, with `db_index=True` in the state
operation. Take the name Django would use from `sqlmigrate` of the generated migration.

If the index is being replaced (for example by a partial index in `Meta.indexes`), put
the `AddIndexConcurrently` before this operation; see `migration-create-before-drop`.

**When not to apply:** on small tables the re-creation is fast and the generated
migration is acceptable. Changing other attributes of the field (`on_delete`,
`related_name`) does not touch the database at all.

**How to detect:** `sqlmigrate` showing `DROP CONSTRAINT` and `ADD CONSTRAINT` with the
same name for a field change; `scripts/check_migration_sql.py` reports it as high.

Reference: [Django Foreign Keys: Safely Migrating Foreign Key](https://hakibenita.com/django-foreign-keys)
