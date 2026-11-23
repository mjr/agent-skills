---
title: Filter on related rows with Exists, not with a join plus distinct()
impact: MEDIUM
risk: correctness
django: ">=5.2"
database: any
tags: exists, distinct, duplicates, join, subquery
sources:
  - https://johnnymetz.com/posts/avoiding-duplicate-objects-in-django-querysets/
tests: test_query_shapes.py
---

## Filter on related rows with Exists, not with a join plus distinct()

Filtering across a reverse or many-to-many relation joins the related table, so a parent
appears once per matching child. Paginated lists show the same item twice, counts are
wrong, and `.get()` raises `MultipleObjectsReturned`. The usual fixes have costs:
`.distinct()` compares every selected column (including large text and JSON fields), and
PostgreSQL's `.distinct('id')` requires the `ORDER BY` to start with `id`.

**Incorrect (a category appears once per matching product):**

```python
Category.objects.filter(products__name__startswith='a')
```

**Correct (a semi-join: each category once, any ordering):**

```python
from django.db.models import Exists, OuterRef

matching = Product.objects.filter(category=OuterRef('pk'), name__startswith='a')
Category.objects.filter(Exists(matching)).order_by('-name')
```

`EXISTS` stops at the first matching child and never duplicates the parent.
`.distinct('id').order_by('name')` fails with "SELECT DISTINCT ON expressions must match
initial ORDER BY expressions"; `Exists` has no such restriction and works on every
database.

**When not to apply:** when you need columns from the child rows, a join is the point;
use `prefetch_related` or `annotate` instead of filtering.

**How to detect:** `.filter()` on `__` lookups through reverse or many-to-many relations,
especially followed by `.distinct()`; duplicated rows in admin lists, exports or API
pages.

Reference: [Avoiding Duplicate Objects in Django Querysets](https://johnnymetz.com/posts/avoiding-duplicate-objects-in-django-querysets/)
