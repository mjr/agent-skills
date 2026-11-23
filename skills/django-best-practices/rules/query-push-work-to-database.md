---
title: Aggregate and compute in the database, not in Python loops
impact: MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: aggregate, filter, extract, database-functions, grouping-sets
sources:
  - https://hakibenita.com/9-django-tips-for-working-with-databases
  - https://hakibenita.com/how-to-use-grouping-sets-in-django
tests: test_query_shapes.py
---

## Aggregate and compute in the database, not in Python loops

Summing, counting by condition or transforming values in Python requires loading every
row. The database does the same work next to the data and returns only the result.

**Incorrect (every row travels to Python):**

```python
sales = Sale.objects.all()
total = sum(s.amount for s in sales)
paid = sum(1 for s in sales if s.status == 'paid')
```

**Correct (one query, conditional aggregates):**

```python
from django.db.models import Count, Q, Sum

Sale.objects.aggregate(
    total=Sum('amount'),
    paid=Count('pk', filter=Q(status='paid')),
)
```

On PostgreSQL the filter compiles to `COUNT(...) FILTER (WHERE ...)`. Pass a `Q` object
to `filter=`; it is the documented form.

Use database functions before writing your own: `Extract('duration', 'epoch')` gives the
seconds of an interval on PostgreSQL (`EXTRACT(EPOCH FROM ...)`), and
`django.db.models.functions` covers dates, strings, math and casts. Subclass `Func` only
for what is missing, and note in the class that its SQL is database-specific.

When the ORM cannot express a query (for example, PostgreSQL `GROUPING SETS` or `ROLLUP`
for totals and subtotals in one pass), write the SQL deliberately with
`connection.cursor()` or `Model.objects.raw()` and parameters. Do not obtain the ORM's
SQL and rewrite it with string operations: it depends on internals and breaks when
Django changes the generated SQL.

**When not to apply:** logic that needs Python (calling services, complex rules) on a
small, already loaded set is fine in Python.

**How to detect:** `sum(`, `len([...])`, `max(` and comprehension filters over querysets;
loops that accumulate values from model instances.

Reference: [9 Django Tips for Working with Databases](https://hakibenita.com/9-django-tips-for-working-with-databases)
