---
title: Limit, count and test for existence in the database
impact: MEDIUM
risk: performance
django: ">=4.2"
database: any
tags: limit, slicing, count, exists, len, bool
sources:
  - https://hakibenita.com/9-django-tips-for-working-with-databases
tests: test_query_shapes.py
---

## Limit, count and test for existence in the database

Python operations on an evaluated queryset load every row first. `list(qs)[:100]`
fetches the whole table to keep 100 rows; `len(qs)` and `if qs:` fetch every row to
answer a question the database answers with one number or one row.

**Incorrect:**

```python
recent = list(Sale.objects.order_by('-created'))[:100]   # All rows, no LIMIT.
total = len(Sale.objects.filter(status='paid'))          # All rows to count them.
if Sale.objects.filter(status='disputed'):               # All rows to test for one.
    alert()
```

**Correct:**

```python
recent = Sale.objects.order_by('-created')[:100]         # LIMIT 100
total = Sale.objects.filter(status='paid').count()       # SELECT COUNT(*)
if Sale.objects.filter(status='disputed').exists():      # LIMIT 1
    alert()
```

To cap a result and know whether it was truncated without a second `COUNT`, fetch one
extra row:

```python
rows = list(Sale.objects.order_by('pk')[: limit + 1])
truncated = len(rows) > limit
rows = rows[:limit]
```

**When not to apply:** if you will iterate the rows anyway, evaluate once and use
`len()` on the list instead of issuing a separate `count()`.

**How to detect:** `list(` around querysets followed by slicing, `len(` of querysets, and
querysets used directly in `if` conditions.

Reference: [9 Django Tips for Working with Databases](https://hakibenita.com/9-django-tips-for-working-with-databases)
