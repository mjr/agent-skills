---
title: Defer large columns the changelist does not show
impact: MEDIUM
risk: performance
django: ">=4.2"
database: any
tags: admin, defer, get_queryset, jsonfield, textfield
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
tests: test_admin_scale.py
---

## Defer large columns the changelist does not show

The changelist selects every column of the model, even those not in `list_display`. A
model with a large `JSONField` (webhook payloads, gateway responses) or `TextField`
transfers all of it for every row of every page, only to show a name and a date.

**Incorrect:**

```python
@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'received_at')
```

**Correct:**

```python
@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'received_at')

    def get_queryset(self, request):
        return super().get_queryset(request).defer('payload')
```

The change form uses the same `get_queryset()`, so it loads the deferred field with one
extra query for that single object and still shows it.

**When not to apply:** never defer a column that `list_display`, `__str__` or a callable
column reads: that would add one query per row (see `query-only-defer`).

**How to detect:** admin classes for models with JSON or long text fields that do not
override `get_queryset`; changelist queries that select those columns.

Reference: [Things You Must Know About Django Admin As Your App Gets Bigger](https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger)
