---
title: Give large changelists a default filter with a SimpleListFilter
impact: LOW
risk: performance
django: ">=5.2"
database: any
tags: admin, list_filter, simplelistfilter, default-filter
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_scale.py
---

## Give large changelists a default filter with a SimpleListFilter

Staff usually look at a slice of a large table (open tickets, this month's orders), but
the changelist opens on everything, paying for the count and the scan each time. A
filter whose default applies when no value is chosen narrows the page without changing
URLs. Older recipes redirect based on `HTTP_REFERER`, which is fragile and surprises
users.

**Correct:**

```python
class OrderedFilter(admin.SimpleListFilter):
    title = 'orders'
    parameter_name = 'ordered'

    def lookups(self, request, model_admin):
        return [('yes', 'With orders'), ('all', 'All')]

    def choices(self, changelist):
        for value, label in self.lookup_choices:
            yield {
                'selected': (self.value() or 'yes') == value,
                'query_string': changelist.get_query_string({self.parameter_name: value}),
                'display': label,
            }

    def queryset(self, request, queryset):
        if (self.value() or 'yes') == 'yes':
            return queryset.filter(Exists(Order.objects.filter(product=OuterRef('pk'))))
        return queryset
```

Overriding `choices()` removes the built-in "All" entry (which would clear the
parameter and fall back to the default) and marks the default as selected.

**When not to apply:** tables that staff search across as a whole; a default that hides
data people expect to see causes support questions.

**How to detect:** large changelists whose first page is rarely what staff need.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
