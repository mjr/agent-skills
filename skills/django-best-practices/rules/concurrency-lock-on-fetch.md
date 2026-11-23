---
title: Lock the row when you fetch it, not after you already have an instance
impact: HIGH
risk: correctness
django: ">=5.2"
database: any
tags: select_for_update, stale-instance, update_fields, classmethod
sources:
  - https://hakibenita.com/django-foreign-keys
tests: test_concurrency_lock_on_fetch.py
---

## Lock the row when you fetch it, not after you already have an instance

An instance in memory is a snapshot. Validating it and saving it later ignores whatever
other requests committed in between, and a plain `save()` writes every column back,
reverting their changes. To make a decision on current data, fetch the row with a lock
inside the transaction that writes it.

**Incorrect (operate on an instance that was fetched earlier):**

```python
class Product(models.Model):
    def edit(self, *, description, edited_by):
        if self.created_by.is_superuser and not edited_by.is_superuser:
            raise NotAllowed()
        self.description = description
        self.last_edited_by = edited_by
        self.save()
```

**What happens:** if another request renamed the product after this instance was loaded,
`save()` sends `UPDATE ... SET name = 'apple', description = ...` and silently restores
the old name. The permission check also ran against data that may be out of date.

**Correct (a classmethod that fetches and locks):**

```python
from django.db import transaction


class Product(models.Model):
    @classmethod
    def edit(cls, pk, *, description, edited_by):
        with transaction.atomic():
            product = (
                cls.objects.select_related('created_by')
                .select_for_update(of=('self',), no_key=True)
                .get(pk=pk)
            )
            if product.created_by.is_superuser and not edited_by.is_superuser:
                raise NotAllowed()
            product.description = description
            product.last_edited_by = edited_by
            product.save(update_fields=['description', 'last_edited_by'])
        return product
```

A concurrent `edit()` waits for the lock and then reads the committed row. See
`concurrency-select-for-update-of` and `concurrency-select-for-update-no-key` for the
lock options.

**When not to apply:** a lock is not free; it serializes every writer of the row. When
the change does not depend on what is stored, `save(update_fields=[...])` alone at least
stops reverting other columns, and a single `QuerySet.update()` needs no instance at all.

**How to detect:** look for instance methods that check state and then call `save()`
without `update_fields`, and for objects fetched in one request phase (a form, a
serializer) and saved after slow work.

Reference: [Django Foreign Keys: Locking Across Relations](https://hakibenita.com/django-foreign-keys)
