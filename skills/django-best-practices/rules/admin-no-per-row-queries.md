---
title: Annotate admin columns instead of querying per row, and link instead of counting
impact: HIGH
risk: performance
django: ">=4.2"
database: any
tags: admin, list_display, annotate, count, format_html, admin-display
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_scale.py
---

## Annotate admin columns instead of querying per row, and link instead of counting

A `list_display` column that calls `.count()`, `.exists()` or `.aggregate()` on a related
manager runs that query for every row on the page. Annotating the changelist queryset
computes the value for the whole page in the list query, and it makes the column
sortable too.

**Incorrect (one COUNT query per row):**

```python
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'orders')

    def orders(self, obj):
        return obj.order_set.count()
```

**Correct (one annotated query, sortable column):**

```python
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'orders')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(orders_n=Count('order'))

    @admin.display(description='orders', ordering='orders_n')
    def orders(self, obj):
        return obj.orders_n
```

When the column only needs to lead somewhere, link to the related changelist filtered by
this object and let that page do the counting:

```python
from django.urls import reverse
from django.utils.html import format_html


@admin.display(description='orders')
def orders_link(self, obj):
    url = reverse('admin:catalog_order_changelist') + f'?product__id__exact={obj.pk}'
    return format_html('<a href="{}">orders</a>', url)
```

`format_html` escapes the values; older recipes set `allow_tags = True`, which no longer
exists.

**When not to apply:** for several aggregates over different relations, use subqueries
(see `query-annotate-aggregates`); two `Count()` annotations over different joins
multiply each other.

**How to detect:** methods in `list_display` that call related managers; slow changelist
pages whose query count grows with `list_per_page`.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
