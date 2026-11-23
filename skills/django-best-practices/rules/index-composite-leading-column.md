---
title: Order composite index columns by how queries filter, and reuse the leading column
impact: MEDIUM
risk: performance
django: ">=5.2"
database: postgresql
tags: composite-index, unique-constraint, column-order, skip-scan, redundant-index
sources:
  - https://hakibenita.com/django-foreign-keys
  - https://hakibenita.com/9-django-tips-for-working-with-databases
tests: test_indexes.py
---

## Order composite index columns by how queries filter, and reuse the leading column

A B-tree index on `(a, b)` serves filters on `a` and on `a` plus `b`. It is not a good
index for `b` alone: PostgreSQL 16 and earlier ignore it and scan the table, and
PostgreSQL 18 can "skip scan" it only when `a` has few distinct values. Two consequences:
a separate index on `a` is redundant, and the column order of a composite index or
unique constraint must start with the column queries filter by.

**Incorrect (a redundant index, and an order that does not match the lookups):**

```python
class Ticket(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)  # Implicit index.
    number = models.IntegerField()

    class Meta:
        constraints = [
            # Lookups are "tickets of account X" and "ticket N of account X".
            models.UniqueConstraint(fields=['number', 'account'], name='ticket_uk'),
        ]
```

**Correct (the constraint's leading column serves the account lookups):**

```python
class Ticket(models.Model):
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        # Indexed by ticket_account_number_uk.
        db_index=False,
    )
    number = models.IntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['account', 'number'], name='ticket_account_number_uk'),
        ]
```

Put first the column used with equality in most queries. Cardinality is a secondary
concern; the index has to match the `WHERE` clauses you actually run.

**When not to apply:** if queries filter by `b` alone often, `b` needs its own index (or
to lead another one). Do not rely on PostgreSQL 18's skip scan as a replacement.

**How to detect:** `EXPLAIN` the important queries; `scripts/pg_index_report.sql` lists
plain indexes whose columns lead another index (`redundant`).

Reference: [9 Django Tips for Working with Databases](https://hakibenita.com/9-django-tips-for-working-with-databases)
