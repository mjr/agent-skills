---
name: django-best-practices
description: Django and PostgreSQL practices, each verified by executable tests on Django 5.2, 6.0 and 6.1. Covers concurrency and locking (select_for_update, F() expressions, IntegrityError races), transactions and side effects (atomic, on_commit, database-backed task queues), safe migrations (locks, concurrent indexes, foreign key index changes, NOT NULL, column defaults, deploy compatibility), signals, query performance (N+1, select_related, prefetch_related, fetch modes, annotations, Exists), indexes, Django REST Framework serializers and pagination, the admin on large tables, and database timeouts and connections. Use when writing, reviewing or refactoring Django models, migrations, querysets, transactions, signal receivers, serializers, admin classes or database settings.
metadata:
  version: "1.0.1"
---

# Django Best Practices

76 rules for Django applications on PostgreSQL, in 10 categories ordered by impact.
Correctness and availability come first: a lost update or a table locked during a deploy
costs more than a slow page. Every rule's claims are checked by an executable test
against a real PostgreSQL, on Django 5.2, 6.0 and 6.1 and PostgreSQL 16 and 18.

## When to apply

- Writing or changing models, migrations, querysets, transactions or signal receivers.
- Reviewing a pull request that touches the database, the admin or DRF serializers.
- Investigating slow pages, lock waits, timeouts, duplicated rows or lost updates.
- Planning a deploy that changes the schema of large tables.

## How to use

1. Find the relevant rules in the quick reference below (or run through the review
   checklist) and read only those files: `rules/<rule-id>.md`. Each has the failure mode,
   an Incorrect example, what happens (often the SQL), a Correct example, when not to
   apply it, and how to detect it.
2. Check the versions. A rule's `django:` field is the oldest supported version where
   its Correct form was verified (5.2 for most), and `database: postgresql` marks
   PostgreSQL-only advice. Older versions may work but were not tested. Look up the
   project's Django version (`requirements*.txt`, `pyproject.toml`, `django.VERSION`)
   before applying a rule marked for a newer one.
3. The project's own rules win. If the project's guidelines (AGENTS.md, CLAUDE.md,
   CONTRIBUTING, lint rules) contradict a rule here, follow the project and point out the
   conflict instead of silently applying this skill.
4. Prefer the bundled scripts over reasoning from memory when the question is "what will
   this migration do" or "which indexes are wasted".

## Scripts

- `scripts/check_migration_sql.py`: flags risky statements in a migration's SQL
  (re-created foreign keys, non-concurrent index changes, `SET NOT NULL`, volatile
  defaults, dropped columns, non-atomic migrations that mix operations). JSON on stdout,
  summary on stderr, exit 1 on high severity. Run `sqlmigrate` against a database
  migrated up to the previous migration, or it may print `(no-op)`:

  ```console
  python manage.py sqlmigrate <app> <migration> | python scripts/check_migration_sql.py
  ```

- `scripts/pg_index_report.sql`: read-only report of unused, redundant, invalid and
  mostly-NULL indexes and of foreign keys without an index:

  ```console
  psql "$DATABASE_URL" -f scripts/pg_index_report.sql
  ```

## Categories

| Priority | Category | Prefix | Impact | Risk |
| --- | --- | --- | --- | --- |
| 1 | Concurrency and locks | `concurrency-` | CRITICAL | correctness |
| 2 | Transactions and side effects | `tx-` | CRITICAL | correctness |
| 3 | Safe migrations | `migration-` | CRITICAL | availability |
| 4 | Signals | `signals-` | HIGH | correctness |
| 5 | Queries and N+1 | `query-` | HIGH | performance |
| 6 | Indexes and foreign keys | `index-` | HIGH | performance, cost |
| 7 | Detection and testing | `detect-` | HIGH | all |
| 8 | Django REST Framework | `drf-` | MEDIUM | performance |
| 9 | Admin at scale | `admin-` | MEDIUM | performance |
| 10 | Database operations | `ops-` | MEDIUM | availability |

## Review checklist

Ask these about any change that touches the database; each points to the rules to open.

1. Does code read a value, decide in Python and write it back (counters, balances,
   stock, "check then create")? `concurrency-f-expressions`,
   `concurrency-conditional-update`, `concurrency-try-create-not-check`
2. Does a `select_for_update()` lack `of=` or `no_key=`? `concurrency-select-for-update-of`,
   `concurrency-select-for-update-no-key`
3. Does anything leave the database (email, HTTP, cache, task to an external broker)
   before the outermost commit, or after the end of a block that may be nested?
   `tx-external-effects-on-commit`, `tx-nested-atomic-side-effects`
4. Could a critical task be lost after the commit? `tx-enqueue-in-transaction-db-queue`
5. Is there a network call inside a transaction or a receiver? `tx-keep-short`,
   `signals-run-in-sender-transaction`
6. Have you read the migration's SQL against a database at the previous state? Does it
   re-create a constraint, build an index without `CONCURRENTLY`, set `NOT NULL`, add a
   volatile default or drop something running code still uses? `migration-review-sql`,
   then the rule the checker names
7. Is a non-atomic migration mixing operations, or dropping an index before creating its
   replacement? `migration-isolate-non-atomic`, `migration-create-before-drop`
8. Does a loop, template, serializer or admin column read a relation or a deferred field
   per row? `query-select-related`, `query-prefetch-related`, `query-only-defer`,
   `drf-queryset-for-nested`, `admin-list-select-related`
9. Does code call `.filter()`, `.count()` or `.first()` on a prefetched relation, or count
   per row? `query-dont-defeat-prefetch`, `drf-method-field-queries`,
   `admin-no-per-row-queries`
10. Does an `annotate()` aggregate over two different multi-valued relations?
    `query-annotate-aggregates`
11. Does a filter across a relation return duplicates, or rely on `distinct()`?
    `query-exists-over-distinct`
12. Is every new `ForeignKey`'s `db_index` an explicit, explained decision?
    `index-explicit-fk-db-index`, `index-fk-index-for-deletes`
13. Do bulk operations skip behavior that `save()` or signals provide?
    `signals-bulk-operations-skip`, `query-bulk-writes`
14. Is raw SQL built with string formatting? `query-raw-sql-params`
15. Are there tests that pin query counts and run `on_commit` callbacks, on PostgreSQL?
    `detect-assert-num-queries`, `detect-capture-on-commit`,
    `detect-test-against-production-engine`
16. Do outbound calls and database statements have timeouts?
    `ops-outbound-timeouts`, `ops-statement-timeout`

## Quick reference

Generated from the rule files; ordered by impact within each category. Rules without a
note apply to Django 5.2+ on any database.

<!-- quick-reference:start -->
### 1. Concurrency and locks (`concurrency-`)

- `concurrency-conditional-update` [CRITICAL] Put the check in the UPDATE instead of reading first
- `concurrency-f-expressions` [CRITICAL] Increment in the database with F(), and do not save the instance again
- `concurrency-try-create-not-check` [CRITICAL] Insert and handle the conflict instead of checking first
- `concurrency-lock-on-fetch` [HIGH] Lock the row when you fetch it, not after you already have an instance
- `concurrency-select-for-update-no-key` [HIGH] Use no_key=True when the locked row's key does not change (PostgreSQL)
- `concurrency-select-for-update-of` [HIGH] Name the tables to lock with select_for_update(of=...)
- `concurrency-skip-locked-queues` [MEDIUM] Claim queue rows with skip_locked so workers do not wait on each other (PostgreSQL)
- `concurrency-update-returning` [LOW-MEDIUM] Use UPDATE ... RETURNING when you need the new value in one round trip (PostgreSQL)

### 2. Transactions and side effects (`tx-`)

- `tx-enqueue-in-transaction-db-queue` [CRITICAL] With a database-backed queue, enqueue critical tasks inside the transaction
- `tx-external-effects-on-commit` [CRITICAL] Run effects outside the database only after the commit
- `tx-nested-atomic-side-effects` [CRITICAL] Leaving your own atomic() block does not mean the data is committed
- `tx-keep-short` [HIGH] Keep network calls and slow work out of transactions
- `tx-durable-entry-points` [MEDIUM] Mark transactions that must commit on exit with durable=True
- `tx-on-commit-bind-arguments` [MEDIUM] Bind callback arguments when registering on_commit, not when it runs
- `tx-on-commit-robust` [MEDIUM] Use on_commit(robust=True) for independent best-effort callbacks

### 3. Safe migrations (`migration-`)

- `migration-fk-db-index-change` [CRITICAL] Change a foreign key's index without re-creating the constraint (PostgreSQL)
- `migration-review-sql` [CRITICAL] Review the SQL a migration will run, against a database at the previous state
- `migration-add-column-defaults` [HIGH] Know how a new column's default is applied before adding it to a big table (PostgreSQL)
- `migration-concurrent-indexes` [HIGH] Build and drop indexes concurrently on busy tables (PostgreSQL)
- `migration-create-before-drop` [HIGH] Create the replacement index before dropping the old one (PostgreSQL)
- `migration-deploy-compatible` [HIGH] Remove and rename columns across releases, not in one
- `migration-isolate-non-atomic` [HIGH] Put non-atomic operations in a migration of their own
- `migration-lock-timeout` [HIGH] Set a lock_timeout for migrations (PostgreSQL)
- `migration-reversible` [HIGH] Give every RunSQL and RunPython a reverse operation
- `migration-set-not-null-in-steps` [HIGH] Make a populated column NOT NULL in steps (PostgreSQL)
- `migration-fk-not-valid` [MEDIUM] Add foreign keys to populated columns as NOT VALID, then validate (PostgreSQL)

### 4. Signals (`signals-`)

- `signals-bulk-operations-skip` [HIGH] Do not rely on save signals for bulk operations
- `signals-run-in-sender-transaction` [HIGH] Remember that receivers run inside the sender's transaction
- `signals-send-robust-and-log` [HIGH] Send custom signals with send_robust and watch its errors
- `signals-decouple-modules` [MEDIUM] Define signals in the sender's module and connect module-level receivers in ready()
- `signals-dispatch-uid` [MEDIUM] Pass dispatch_uid when a receiver can be connected more than once
- `signals-receivers-exit-early` [MEDIUM] Connect receivers to a sender and return early when the event is not theirs
- `signals-serializable-args` [MEDIUM] Send primary keys and plain values in signals, not model instances
- `signals-name-what-happened` [LOW-MEDIUM] Name signals after what happened, not what should happen next

### 5. Queries and N+1 (`query-`)

- `query-annotate-aggregates` [HIGH] Annotate counts and sums, and never combine two multi-valued joins
- `query-bulk-writes` [HIGH] Write many rows with bulk_create and bulk_update
- `query-dont-defeat-prefetch` [HIGH] Work on the prefetched objects, not on a new query
- `query-fetch-modes` [HIGH] On Django 6.1+, use fetch modes to batch or forbid lazy loads (Django >=6.1)
- `query-prefetch-related` [HIGH] Load reverse and many-to-many relations with prefetch_related
- `query-raw-sql-params` [HIGH] Pass values to raw SQL as parameters, never by formatting strings
- `query-select-related` [HIGH] Join forward relations you will read with select_related
- `query-exists-over-distinct` [MEDIUM] Filter on related rows with Exists, not with a join plus distinct()
- `query-iterator-large-sets` [MEDIUM] Stream large querysets with iterator(chunk_size=...)
- `query-limit-in-db` [MEDIUM] Limit, count and test for existence in the database
- `query-only-defer` [MEDIUM] Skip heavy columns with only()/defer() or values(), and never read them later
- `query-prefetch-object` [MEDIUM] Shape prefetches with Prefetch(queryset=..., to_attr=...)
- `query-push-work-to-database` [MEDIUM] Aggregate and compute in the database, not in Python loops

### 6. Indexes and foreign keys (`index-`)

- `index-explicit-fk-db-index` [HIGH] Set db_index explicitly on every ForeignKey and say why
- `index-fk-index-for-deletes` [HIGH] Keep foreign key indexes that deletes depend on
- `index-audit-unused-and-duplicate` [MEDIUM] Audit indexes for unused, redundant, invalid and sparse ones (PostgreSQL)
- `index-composite-leading-column` [MEDIUM] Order composite index columns by how queries filter, and reuse the leading column (PostgreSQL)
- `index-partial-sparse` [MEDIUM] Use partial indexes for columns that are mostly NULL or mostly one value (PostgreSQL)
- `index-unique-constraint` [MEDIUM] Declare uniqueness with named UniqueConstraints
- `index-brin-correlated` [LOW-MEDIUM] Consider BRIN for large tables filtered by an append-ordered column (PostgreSQL)

### 7. Detection and testing (`detect-`)

- `detect-assert-num-queries` [HIGH] Assert that query counts do not grow with the number of rows
- `detect-capture-on-commit` [HIGH] Run on_commit callbacks in tests explicitly
- `detect-test-against-production-engine` [HIGH] Run database tests on the same engine as production
- `detect-explain` [MEDIUM] Check the plan with QuerySet.explain() before adding or dropping an index
- `detect-sql-logging` [MEDIUM] Log SQL in development, knowing it only works with DEBUG on
- `detect-system-checks` [MEDIUM] Turn conventions into system checks
- `detect-sentry-n-plus-one` [LOW-MEDIUM] Know what an APM's N+1 detector reports and what it misses

### 8. Django REST Framework (`drf-`)

- `drf-method-field-queries` [HIGH] Do not query inside SerializerMethodField; annotate and read the attribute
- `drf-queryset-for-nested` [HIGH] Load what nested serializers read in the view's get_queryset
- `drf-pagination-count` [MEDIUM] Paginate every list, order it, and know what the page count costs
- `drf-plain-serializer-hot-reads` [MEDIUM] Use lighter serialization on hot read-only endpoints
- `drf-read-only-fields` [LOW-MEDIUM] Mark fields that are never written as read-only

### 9. Admin at scale (`admin-`)

- `admin-fk-widgets` [HIGH] Use autocomplete_fields or raw_id_fields for foreign keys to large tables
- `admin-list-select-related` [HIGH] Cover relations read by list_display callables with list_select_related
- `admin-no-per-row-queries` [HIGH] Annotate admin columns instead of querying per row, and link instead of counting
- `admin-defer-heavy-fields` [MEDIUM] Defer large columns the changelist does not show
- `admin-show-full-result-count` [MEDIUM] Turn off show_full_result_count on large tables
- `admin-date-hierarchy` [LOW] Index the date_hierarchy column with a plain B-tree, and mind the year links
- `admin-default-filters` [LOW] Give large changelists a default filter with a SimpleListFilter

### 10. Database operations (`ops-`)

- `ops-outbound-timeouts` [HIGH] Give every outbound HTTP call a timeout
- `ops-statement-timeout` [HIGH] Bound query and idle-transaction time on every connection (PostgreSQL)
- `ops-persistent-connections` [MEDIUM] Reuse database connections with CONN_MAX_AGE or the connection pool (PostgreSQL)
<!-- quick-reference:end -->
