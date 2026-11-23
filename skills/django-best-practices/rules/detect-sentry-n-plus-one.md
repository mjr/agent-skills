---
title: Know what an APM's N+1 detector reports and what it misses
impact: LOW-MEDIUM
risk: performance
django: ">=4.2"
database: any
tags: sentry, apm, n+1, monitoring
sources:
  - https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/
tests: "none: describes the behavior of an external monitoring service"
---

## Know what an APM's N+1 detector reports and what it misses

Production monitoring finds N+1 problems that tests did not cover, but detectors use
thresholds. Sentry's N+1 detector, for example, reports a transaction only when it sees
repeated, sequential database spans with similar SQL that together take more than 50 ms
and number more than about five, preceded by a "source" span, and only when spans carry
the full, parameterized SQL. Smaller or faster repetitions are not reported.

**Incorrect (treating "no N+1 issues in Sentry" as proof):**

```text
"Sentry shows no N+1, so the list endpoint is fine."
```

**Correct (use it as a second net, not the first):**

- Keep query-count tests for important views (see `detect-assert-num-queries`); they
  catch the problem before deploy and at any size.
- Treat each reported N+1 issue as a missing `select_related`/`prefetch_related` (see
  `query-select-related`, `query-prefetch-related`) or a missing bulk write (see
  `query-bulk-writes`), and add a query-count test when fixing it.
- Thresholds can be tuned per project in Sentry's performance settings.

**When not to apply:** this applies to any APM with automatic detection; check your
tool's documented thresholds.

**How to detect:** in Sentry, filter issues by the N+1 query category; look at the
"repeating spans" to find the code path.

Reference: [Sentry: N+1 Queries](https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/)
