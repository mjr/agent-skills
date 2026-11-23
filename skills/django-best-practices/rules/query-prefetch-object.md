---
title: Shape prefetches with Prefetch(queryset=..., to_attr=...)
impact: MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: prefetch, to_attr, select_related, filtered-prefetch
sources:
  - https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django
tests: test_query_relations.py
---

## Shape prefetches with Prefetch(queryset=..., to_attr=...)

A plain prefetch loads every related row with the default ordering and nothing joined.
A `Prefetch` object controls the query: join the next level with `select_related`,
filter or order the related rows, and store a filtered result under its own attribute.

**Incorrect (three queries, and filtering later defeats the prefetch):**

```python
categories = Category.objects.prefetch_related('products__created_by')
for category in categories:
    active = category.products.filter(is_active=True)  # New query per category.
```

**Correct (two queries, filtered in the database):**

```python
from django.db.models import Prefetch

active_products = Prefetch(
    'products',
    queryset=Product.objects.filter(is_active=True).select_related('created_by'),
    to_attr='active_products',
)
for category in Category.objects.prefetch_related(active_products):
    for product in category.active_products:  # A plain list.
        product.created_by.username
```

With `to_attr`, the result is a list on that attribute and the relation itself
(`category.products.all()`) is untouched. Without `to_attr`, the filtered rows replace the
relation's cache, so code elsewhere that expects all products silently gets the filtered
ones.

**Choose a `to_attr` that no field, relation or property uses.** Django does not report a
clash: with `to_attr='name'` or `to_attr='order_set'` the prefetched list is silently
discarded and the attribute keeps its usual value. A suffix such as `_list` or a
descriptive name (`active_products`) avoids it.

**When not to apply:** a plain string prefetch is enough when you need all related rows
and nothing from the next level.

**How to detect:** `.filter()`, `.exclude()` or `.order_by()` on related managers after a
prefetch; chained prefetches (`'a__b'`) whose second level is a forward relation.

Reference: [All You Need to Know About Prefetching in Django](https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django)
