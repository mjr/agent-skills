---
title: Cover relations read by list_display callables with list_select_related
impact: HIGH
risk: performance
django: ">=4.2"
database: any
tags: admin, list_display, list_select_related, n+1
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_scale.py
---

## Cover relations read by list_display callables with list_select_related

The admin changelist joins foreign keys listed by name in `list_display` on its own. It
cannot see inside methods and callables: a column that shows `obj.created_by.username`
or `obj.category.parent.name` runs one query per row of the page, 100 by default.

**Incorrect (the callable's relation is loaded once per row):**

```python
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'author')  # 'category' is joined automatically.

    @admin.display(description='author')
    def author(self, obj):
        return obj.created_by.username  # One query per row.
```

**Correct:**

```python
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'author')
    list_select_related = ('category', 'created_by')

    @admin.display(description='author', ordering='created_by__username')
    def author(self, obj):
        return obj.created_by.username
```

Setting `list_select_related` replaces the automatic behavior, so list every relation the
page reads, including the plain foreign key columns. Reverse and many-to-many relations
need `get_queryset()` with `prefetch_related()` or annotations (see
`admin-no-per-row-queries`).

**When not to apply:** relations read only on the change form do not affect the list.

**How to detect:** `list_display` entries that are methods or callables touching
`obj.<relation>`; changelist query counts that grow with `list_per_page`.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
