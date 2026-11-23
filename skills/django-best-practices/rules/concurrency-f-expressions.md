---
title: Increment in the database with F(), and do not save the instance again
impact: CRITICAL
risk: correctness
django: ">=4.2"
database: any
tags: f-expression, counter, lost-update, returning
sources:
  - https://hakibenita.com/django-concurrency
tests: test_concurrency_f_expressions.py
---

## Increment in the database with F(), and do not save the instance again

`obj.hits += 1; obj.save()` reads the value into Python and writes it back. Two requests
that read the same value both write the same result, and one increment is lost. An `F()`
expression sends the arithmetic to the database, which applies each update to the current
row value.

**Incorrect (read, modify, write):**

```python
url = ShortUrl.objects.get(key=key)
url.hits += 1
url.save(update_fields=['hits'])
```

**What happens:** both requests read `hits = 0` and both send `UPDATE ... SET hits = 1`.
The counter ends at 1 after two hits.

**Correct (let the database compute the new value):**

```python
from django.db.models import F

ShortUrl.objects.filter(key=key).update(hits=F('hits') + 1)
```

This is a single `UPDATE ... SET hits = hits + 1` and needs no instance. When you already
hold the instance:

```python
url.hits = F('hits') + 1
url.save(update_fields=['hits'])
```

**The trap after saving an expression**, which differs by version:

- **Django 5.2 and earlier:** after `save()` the attribute still holds the expression. A
  second `save()` of the same instance sends `hits = hits + 1` again and counts twice.
  Call `url.refresh_from_db(fields=['hits'])` before reading or saving it again.
- **Django 6.0 and later:** `save()` adds `RETURNING` and puts the new integer back on the
  attribute. A second `save()` now sends the literal value (`SET hits = 5`), which is a
  read-modify-write again: an increment made by another request in between is lost.

In both versions, do not reuse an instance for further saves after assigning an `F()`
expression; prefer `QuerySet.update()`, or pass `update_fields` that leave the counter out.

**When not to apply:** when the decision depends on the current value ("withdraw only if
the balance is enough"), an unconditional `F()` update is not enough; see
`concurrency-conditional-update`.

**How to detect:** search for `+= 1`, `-= 1` or `= obj.field + ...` followed by `save()`
on counters, stock, balances and quotas. In tests, run two updates through separate
connections and assert the final value.

Reference: [Handling Concurrency Without Locks](https://hakibenita.com/django-concurrency)
