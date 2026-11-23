---
title: Audit indexes for unused, redundant, invalid and sparse ones
impact: MEDIUM
risk: cost
django: ">=5.2"
database: postgresql
tags: index, audit, pg_stat_user_indexes, redundant, invalid
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_indexes.py
---

## Audit indexes for unused, redundant, invalid and sparse ones

Indexes accumulate: one per foreign key by default, more for each slow query someone
fixed, leftovers from failed concurrent builds. Each one slows every write and competes
for memory. Indexes are not visible in the models in full, so they have to be audited in
the database.

**Correct (run the bundled report against production or a recent copy):**

```console
$ psql "$DATABASE_URL" -f scripts/pg_index_report.sql
   finding        | table_name      | index_name              | detail
------------------+-----------------+-------------------------+-------------------------------
 fk-without-index | orders_item     | orders_item_owner_id_fk | no index starts with owner_id
 invalid          | orders_order    | order_created_ix        | drop it with DROP INDEX ...
 mostly-null      | catalog_product | product_edited_by_ix    | 99% NULL, size 6440 kB
 redundant        | tickets_ticket  | ticket_account_ix       | its columns lead ticket_uk
 unused           | tickets_ticket  | ticket_account_ix       | idx_scan = 0, size 2 MB; ...
```

How to act on each finding:

- **unused**: confirm with the statistics of every server that receives queries
  (replicas keep their own) and over a period that includes rare jobs; check whether it
  backs a foreign key used by deletes (`index-fk-index-for-deletes`). Then drop it with
  `RemoveIndexConcurrently` or the foreign key migration pattern.
- **redundant**: its columns lead another index; drop it.
- **invalid**: left by a failed concurrent build; drop and rebuild it
  (`migration-concurrent-indexes`).
- **mostly-null**: replace with a partial index (`index-partial-sparse`).
- **fk-without-index**: add one if rows of the referenced table are ever deleted.

**When not to apply:** statistics reset on server restarts in some setups and are
per-server; a short observation window misses monthly jobs. Treat findings as
candidates, never as automatic drops.

**How to detect:** schedule the report (monthly, or after major releases) and review its
output like a code review.

Reference: [Django Foreign Keys](https://hakibenita.com/django-foreign-keys)
