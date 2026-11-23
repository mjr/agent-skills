---
title: Index the date_hierarchy column with a plain B-tree, and mind the year links
impact: LOW
risk: performance
django: ">=4.2"
database: any
tags: admin, date_hierarchy, index, date_trunc
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_changelist_queries.py
---

## Index the date_hierarchy column with a plain B-tree, and mind the year links

Older advice indexed `EXTRACT(...)` expressions to support `date_hierarchy`. Current
Django (verified on 5.2, 6.0 and 6.1) filters every drill-down level with a plain range
on the column (`paid_at >= '2026-03-01' AND paid_at < '2026-04-01'`), so a regular index
on the column serves it and expression indexes are unnecessary. The expensive query is
another one: at the top level, the admin runs `SELECT DISTINCT DATE_TRUNC('year', ...)`
over the whole table to build the year links.

**Correct:**

```python
class Payment(models.Model):
    paid_at = models.DateTimeField(null=True, db_index=True)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    date_hierarchy = 'paid_at'
```

**When not to apply:** on very large tables, the top-level `DISTINCT DATE_TRUNC` still
reads every row; combine `date_hierarchy` with a default filter (see
`admin-default-filters`) or drop it for that admin.

**How to detect:** `date_hierarchy` on large tables; the `DATE_TRUNC` query among the
changelist's queries when opened without filters.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
