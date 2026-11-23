---
title: Review the SQL a migration will run, against a database at the previous state
impact: CRITICAL
risk: availability
django: ">=5.2"
database: any
tags: sqlmigrate, review, locks, check_migration_sql
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_migration_fk_db_index_change.py, test_migration_review_sql_script.py
---

## Review the SQL a migration will run, against a database at the previous state

A migration file says what changes in Django's model state; it does not say what runs
in the database. An innocent `AlterField` can drop and re-create a foreign key, rewrite a
table or take an `ACCESS EXCLUSIVE` lock for minutes. `sqlmigrate` shows the real SQL,
but only when it runs against a database that is already at the previous migration:
Django reads constraint and index names from the live database, and when it cannot find
them it prints `(no-op)` for an operation that will do a lot in production.

**Incorrect (reviewing the migration file, or sqlmigrate on an empty database):**

```console
$ python manage.py sqlmigrate catalog 0002     # fresh database, tables not created yet
-- Alter field parent on child
-- (no-op)
```

**Correct (review against a database at the previous migration):**

```console
$ python manage.py migrate catalog 0001        # or a restored copy of production
$ python manage.py sqlmigrate catalog 0002
SET CONSTRAINTS "child_parent_id_fk" IMMEDIATE;
ALTER TABLE "child" DROP CONSTRAINT "child_parent_id_fk";
DROP INDEX IF EXISTS "child_parent_id_4b951ec7";
ALTER TABLE "child" ADD CONSTRAINT "child_parent_id_fk" FOREIGN KEY ...
```

Pipe the output through the bundled checker, which flags the statements covered by the
other `migration-` rules and exits with 1 on high-severity findings:

```console
$ python manage.py sqlmigrate catalog 0002 | python scripts/check_migration_sql.py
[high] migration-fk-db-index-change: The foreign key is dropped and re-created ...
```

What to look for: `DROP CONSTRAINT` followed by `ADD CONSTRAINT` (constraint
re-creation), `CREATE INDEX` or `DROP INDEX` without `CONCURRENTLY`, `SET NOT NULL`,
`ALTER COLUMN ... TYPE`, volatile defaults, `ADD CONSTRAINT ... FOREIGN KEY` without
`NOT VALID`, and `DROP COLUMN` or renames that running code may still use.

**When not to apply:** migrations that only create new tables, or change tables known to
stay small, can skip the detailed review; the checker ignores statements on tables the
same migration creates.

**How to detect:** add the review to the pull request checklist, or run `sqlmigrate`
plus the checker in CI against a database migrated to the target branch's state.

Reference: [Django Foreign Keys: Identifying Blocking Migrations](https://hakibenita.com/django-foreign-keys)
