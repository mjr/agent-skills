---
title: Check the plan with QuerySet.explain() before adding or dropping an index
impact: MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: explain, analyze, buffers, query-plan, index
sources:
  - https://docs.djangoproject.com/en/stable/ref/models/querysets/#explain
tests: test_detect.py
---

## Check the plan with QuerySet.explain() before adding or dropping an index

Whether an index helps depends on the query, the data distribution and the PostgreSQL
version; guessing leads to indexes that are never used and to dropping ones that are.
`QuerySet.explain()` shows the plan of the exact SQL Django sends.

**Correct:**

```python
print(Ticket.objects.filter(account=account, number=42).explain())
# Index Scan using ticket_account_number_uk on indexlab_ticket ...

print(Ticket.objects.filter(number=42).explain(analyze=True, buffers=True))
# Seq Scan on indexlab_ticket ... (actual time=... rows=1) Buffers: shared hit=148
```

`analyze=True` executes the query and reports real row counts and timings;
`buffers=True` shows how many pages were read, which is the most reliable measure of the
work done. Compare plans before and after a change, on data shaped like production (an
empty development table always gets a sequential scan).

**When not to apply:** `analyze=True` runs the query: do not use it on statements with
side effects, and expect slow queries to take their full time. Plans differ between
PostgreSQL versions (for example, version 18 can skip-scan composite indexes), so check
on the version you run.

**How to detect:** index additions or removals in pull requests without a plan or a
measurement attached.

Reference: [QuerySet.explain()](https://docs.djangoproject.com/en/stable/ref/models/querysets/#explain)
