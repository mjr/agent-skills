---
title: Name the tables to lock with select_for_update(of=...)
impact: HIGH
risk: availability
django: ">=4.2"
database: any             # PostgreSQL, MySQL 8.0.1+, Oracle; NotSupportedError elsewhere
tags: select_for_update, select_related, locking
sources:
  - https://hakibenita.com/django-foreign-keys
  - https://hakibenita.com/9-django-tips-for-working-with-databases
tests: test_concurrency_select_for_update_scope.py
---

## Name the tables to lock with select_for_update(of=...)

`SELECT ... FOR UPDATE` locks the rows of every table in the query. Combined with
`select_related()`, locking a product also locks its category, its author and every other
joined row, and blocks unrelated updates to them until the transaction ends.

**Incorrect (locks the joined user too):**

```python
product = (
    Product.objects.select_related('created_by')
    .select_for_update()
    .get(pk=pk)
)
```

**What happens:** while this transaction is open, `User.objects.filter(pk=...).update(...)`
on the product's author waits. On a busy table, every login or profile change of a user
who created a product being edited queues behind the edit.

**Correct (lock only the queryset's own rows):**

```python
product = (
    Product.objects.select_related('created_by')
    .select_for_update(of=('self',))
    .get(pk=pk)
)
```

`'self'` means the queryset's model; add related names (`of=('self', 'category')`) only
for rows you will also modify.

Write `of=('self',)` even when there is no `select_related()` today: a join added later
would silently widen the lock.

**When not to apply:** when the transaction does update the related row, lock it too, by
naming it in `of`.

**How to detect:** search for `select_for_update()` without `of=`. Tests that run on
SQLite cannot catch this: Django ignores `select_for_update()` on backends without row
locks, so locking behavior must be tested against the production database engine. Prove the scope in a
test: hold the lock in one connection and try to update a related row from another with
`SET lock_timeout`.

Reference: [Django Foreign Keys: Locking Across Relations](https://hakibenita.com/django-foreign-keys)
