---
title: Set db_index explicitly on every ForeignKey and say why
impact: HIGH
risk: cost
django: ">=5.2"
database: any
tags: foreign-key, db_index, index, review
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_indexes.py
---

## Set db_index explicitly on every ForeignKey and say why

Django creates an index on every `ForeignKey` unless told otherwise. Each index costs
disk, memory and time on every insert and update, and many are redundant (the column is
already the leading column of another index) or rarely useful. Others look useless but
are essential, because deletes depend on them. Writing the choice and its reason makes
each one a decision that the next reader does not have to rediscover.

**Incorrect (an implicit index nobody decided on):**

```python
class Ticket(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
```

**Correct (explicit, with the reason):**

```python
class Ticket(models.Model):
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        # Indexed by ticket_account_number_uk (account is its leading column).
        db_index=False,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        # Used when a user is deleted, to check for their tickets.
        db_index=True,
    )
```

Writing `db_index=True` changes nothing in the database (it is the default), so making
existing foreign keys explicit generates no SQL. Changing an existing one to `False`
does; see `migration-fk-db-index-change` before doing it.

**When not to apply:** nothing to avoid; the cost is one line per field. A system check
can enforce it (see `detect-system-checks`).

**How to detect:** `ForeignKey(` declarations without `db_index=`; run
`scripts/pg_index_report.sql` for redundant and unused indexes.

Reference: [Django Foreign Keys: Indexes on Foreign Keys](https://hakibenita.com/django-foreign-keys)
