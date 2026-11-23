---
title: Declare uniqueness with named UniqueConstraints
impact: MEDIUM
risk: correctness
django: ">=5.2"
database: any
tags: uniqueconstraint, unique_together, partial-unique, nulls_distinct
sources:
  - https://hakibenita.com/django-foreign-keys
  - https://docs.djangoproject.com/en/stable/ref/models/constraints/#uniqueconstraint
tests: test_indexes.py
---

## Declare uniqueness with named UniqueConstraints

`unique_together` is kept for compatibility, and the documentation says it may be
deprecated. `UniqueConstraint` does everything it does plus partial uniqueness,
expressions and NULL handling, and it carries a name you choose, which shows up in
errors and can be referenced from code (see `concurrency-try-create-not-check`).

**Incorrect:**

```python
class Meta:
    unique_together = [('account', 'number')]
```

**Correct:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=['account', 'number'], name='ticket_account_number_uk'),
    ]
```

Two capabilities `unique_together` lacks:

```python
# Unique among active rows only: history rows may repeat.
models.UniqueConstraint(
    fields=['user', 'team'],
    condition=models.Q(active=True),
    name='membership_one_active_per_team_uk',
)

# NULL counts as a value: at most one row without a code (Django 5.0+, PostgreSQL 15+).
models.UniqueConstraint(fields=['code'], name='voucher_code_uk', nulls_distinct=False)
```

By default SQL treats NULLs as distinct, so a plain unique constraint allows any number
of NULL rows.

**When not to apply:** converting an existing `unique_together` rebuilds the index; on a
large table do it with the concurrent-index care in `migration-concurrent-indexes`.

**How to detect:** `unique_together` in `Meta`; unique constraints without explicit names;
nullable unique fields where duplicates of NULL would be a bug.

Reference: [UniqueConstraint](https://docs.djangoproject.com/en/stable/ref/models/constraints/#uniqueconstraint)
