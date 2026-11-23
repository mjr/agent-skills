---
title: Use autocomplete_fields or raw_id_fields for foreign keys to large tables
impact: HIGH
risk: performance
django: ">=5.2"
database: any
tags: admin, autocomplete_fields, raw_id_fields, select, foreign-key
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_scale.py
---

## Use autocomplete_fields or raw_id_fields for foreign keys to large tables

The default widget for a foreign key in the admin form is a `<select>` with one option
per row of the related table. For a foreign key to users or orders, opening the change
form loads the whole table and renders a page of megabytes; with inlines it happens once
per inline row.

**Incorrect (every user becomes an option):**

```python
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    pass  # created_by renders as <select> with all users.
```

**Correct:**

```python
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ('created_by',)
```

`autocomplete_fields` loads options on demand through the related model's admin, which
must be registered with `search_fields` (a system check reports it otherwise).
`raw_id_fields` shows an ID input with a lookup popup and needs nothing else. For
fields that must not change after creation, `readonly_fields` avoids the widget
entirely.

**When not to apply:** small, stable related tables (statuses, countries) are fine as
selects.

**How to detect:** foreign keys in admin forms and inlines to tables with thousands of
rows; change forms that load slowly or whose HTML is very large; an unbounded
`SELECT ... FROM <related table>` among the form's queries.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
