---
title: Imperative title that states the rule
impact: MEDIUM            # CRITICAL | HIGH | MEDIUM-HIGH | MEDIUM | LOW-MEDIUM | LOW
risk: performance         # correctness | availability | performance | cost
django: ">=4.2"           # oldest version where the Correct form works as shown
database: any             # any | postgresql
tags: tag-one, tag-two
sources:
  - https://example.com/article
tests: test_file_name.py  # in packages/django-best-practices-tests/tests/rules/, or "none: <reason>"
---

## Imperative title that states the rule

Two to four sentences: the failure mode and why it happens. Say what goes wrong, not
only what to type.

**Incorrect (what is wrong with it):**

```python
# Code that looks reasonable and fails.
```

**What happens:** the SQL Django sends or the behavior at runtime (a lock, a full scan,
one query per row, a lost update). Show the SQL when it is the evidence.

**Correct (why this works):**

```python
# The fix.
```

**When not to apply:** the limits of the rule, the trade-offs, and the cases where the
Incorrect form is acceptable.

**How to detect:** how to find the problem in an existing codebase or catch it in a
test (sqlmigrate, assertNumQueries, EXPLAIN, a grep pattern).

Reference: [Title](https://example.com)
