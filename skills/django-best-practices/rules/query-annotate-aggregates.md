---
title: Annotate counts and sums, and never combine two multi-valued joins
impact: HIGH
risk: correctness
django: ">=4.2"
database: any
tags: annotate, count, subquery, join-multiplication, n+1
sources:
  - https://docs.djangoproject.com/en/stable/topics/db/aggregation/#combining-multiple-aggregations
tests: test_query_relations.py
---

## Annotate counts and sums, and never combine two multi-valued joins

`obj.items.count()` per row is an N+1 of `COUNT` queries; annotating the queryset computes
all counts in one query. But two aggregates over different multi-valued relations in the
same `annotate()` join both tables at once, so each row is repeated once per combination
and both numbers come out multiplied: wrong data, with no error.

**Incorrect (one count query per product):**

```python
for product in Product.objects.all():
    product.order_set.count()
```

**Incorrect (one query, wrong numbers):**

```python
Product.objects.annotate(tags_n=Count('tags'), orders_n=Count('order'))
# A product with 3 tags and 2 orders reports 6 and 6.
```

**Correct (one aggregate per relation, computed independently):**

```python
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce

orders = (
    Order.objects.filter(product=OuterRef('pk'))
    .order_by()
    .values('product')
    .annotate(n=Count('pk'))
    .values('n')
)
Product.objects.annotate(
    tags_n=Count('tags'),
    orders_n=Coalesce(Subquery(orders), 0),
)
```

`Count(..., distinct=True)` also fixes counts (3 and 2 above), but not `Sum` or `Avg`
over the multiplied rows, and it still builds the large join. Subqueries keep each
aggregate correct and the join small.

**When not to apply:** a single aggregate over one relation in an `annotate()` is safe.

**How to detect:** `annotate()` calls with two or more aggregates whose lookups go through
different reverse or many-to-many relations; `.count()`, `.exists()` or `aggregate()` on
related managers inside loops and serializer methods.

Reference: [Combining multiple aggregations](https://docs.djangoproject.com/en/stable/topics/db/aggregation/#combining-multiple-aggregations)
