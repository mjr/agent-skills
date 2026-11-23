---
title: Use no_key=True when the locked row's key does not change
impact: HIGH
risk: availability
django: ">=4.2"
database: postgresql
tags: select_for_update, no_key, foreign-key, locking
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_concurrency_select_for_update_scope.py
---

## Use no_key=True when the locked row's key does not change

Inserting a row that references another one (a product created by a user, an order for a
product) makes PostgreSQL take a `FOR KEY SHARE` lock on the referenced row, to make sure
it is not deleted or its key changed meanwhile. A plain `FOR UPDATE` conflicts with that
lock, so while one transaction edits a user, nobody can create anything that points to
that user.

**Incorrect (blocks every insert that references the row):**

```python
with transaction.atomic():
    product = Product.objects.select_for_update(of=('self',)).get(pk=pk)
    ...
```

**What happens:** while the product is being edited, creating an `Order` for it waits for
the lock. For a popular product, checkout stops while someone edits the description.

**Correct (a lock that still serializes updates but allows references):**

```python
with transaction.atomic():
    product = Product.objects.select_for_update(of=('self',), no_key=True).get(pk=pk)
    ...
```

`FOR NO KEY UPDATE` still blocks other `UPDATE`s and `select_for_update()` calls on the
row, so concurrent edits remain serialized; it only stops blocking inserts and updates in
tables that reference it.

**When not to apply:** when the transaction changes the primary key, or a unique column
that a foreign key points to, or deletes the row, use plain `select_for_update()`.
`no_key` is PostgreSQL-only; on other databases Django raises `NotSupportedError`.

**How to detect:** search for `select_for_update(` without `no_key=True` on models that
other tables reference. In a test, hold the lock in one connection and insert a
referencing row from another with `SET lock_timeout`.

Reference: [Django Foreign Keys: Permissive No Key Locks](https://hakibenita.com/django-foreign-keys)
