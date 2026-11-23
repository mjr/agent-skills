---
title: Log SQL in development, knowing it only works with DEBUG on
impact: MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: logging, debug, sql, django-debug-toolbar
sources:
  - https://hakibenita.com/things-you-must-know-about-django-admin-as-your-app-gets-bigger
  - https://docs.djangoproject.com/en/stable/ref/logging/#django-db-backends
tests: test_detect.py
---

## Log SQL in development, knowing it only works with DEBUG on

Seeing the queries a page runs is the fastest way to find N+1 problems and unexpected
scans. The `django.db.backends` logger logs every SQL statement at `DEBUG` level, without
any extra dependency, but only when `settings.DEBUG` is `True`: with `DEBUG = False`,
nothing is logged even if the logger is configured.

**Correct (development settings):**

```python
LOGGING = {
    'version': 1,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'django.db.backends': {'handlers': ['console'], 'level': 'DEBUG'},
    },
}
```

For a per-page view with timings and stack traces, use django-debug-toolbar in
development. In a shell or a test, `CaptureQueriesContext` captures queries regardless
of `DEBUG`.

**When not to apply:** never enable SQL logging in production: it logs parameter values
(personal data, tokens) and slows every query. Use the database's own tools there
(`pg_stat_statements`, slow query log) or an APM.

**How to detect:** development setups without any way to see the SQL; developers
debugging performance by reading code alone.

Reference: [django.db.backends logger](https://docs.djangoproject.com/en/stable/ref/logging/#django-db-backends)
