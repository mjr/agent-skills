---
title: Join forward relations you will read with select_related
impact: HIGH
risk: performance
django: ">=4.2"
database: any
tags: n+1, select_related, foreignkey, onetoone
sources:
  - https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/
  - https://hakibenita.com/all-you-need-to-know-about-prefetching-in-django
tests: test_query_relations.py
---

## Join forward relations you will read with select_related

Accessing a `ForeignKey` or `OneToOneField` that was not loaded runs a query for that one
object. In a loop over a queryset, in a template or in a serializer, that is one query
per row: the N+1 problem. `select_related()` joins the related tables into the original
query.

**Incorrect (one query for the products, one more per product):**

```python
for product in Product.objects.all():
    print(product.category.name, product.created_by.username)
```

**Correct (one query with joins):**

```python
for product in Product.objects.select_related('category', 'created_by'):
    print(product.category.name, product.created_by.username)
```

Follow chains with `__` (`select_related('category__parent')`). It only works for
forward single-valued relations; asking for a many-to-many or reverse relation raises
`FieldError` (use `prefetch_related`, see `query-prefetch-related`).

**When not to apply:** a join that multiplies wide rows (several large related tables)
can cost more than a separate query; for rarely read relations, load them only where
they are used. On Django 6.1+, `fetch_mode(FETCH_PEERS)` batches lazy forward relations
automatically (see `query-fetch-modes`).

**How to detect:** attribute access on relations inside loops, templates
(`{{ product.category.name }}`) and serializer fields (`source='category.name'`) without a
matching `select_related`. Count queries in a test of the list view (see
`detect-assert-num-queries`).

Reference: [Sentry: N+1 Queries](https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/)
