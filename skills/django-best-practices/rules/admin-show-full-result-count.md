---
title: Turn off show_full_result_count on large tables
impact: MEDIUM
risk: performance
django: ">=4.2"
database: any
tags: admin, count, show_full_result_count, changelist
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_changelist_queries.py
---

## Turn off show_full_result_count on large tables

When a changelist is filtered or searched, the admin shows "5 results (1,234,567 total)",
and computing that total runs an unfiltered `COUNT(*)` over the whole table on every page
load, in addition to the count of the filtered results. On a large PostgreSQL table, that
count alone can take seconds.

**Incorrect (the default):**

```python
@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_filter = ('kind',)
```

**Correct:**

```python
@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_filter = ('kind',)
    show_full_result_count = False  # Shows "Show all" instead of the total.
```

The filtered count still runs (pagination needs it). If that one is also slow, the
filters need indexes, or the changelist needs a default filter that narrows it (see
`admin-default-filters`).

**When not to apply:** small tables, where the total is cheap and useful.

**How to detect:** changelists of large tables; a `SELECT COUNT(*) FROM <table>` without a
`WHERE` clause among the changelist's queries.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
