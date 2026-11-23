# Sections

Categories in priority order. The prefix is the rule filename prefix. Correctness and
availability come before performance: a lost update or a locked table costs more than a
slow page.

## 1. Concurrency and locks (concurrency-)

**Impact:** CRITICAL
**Risk:** correctness
**Description:** Several processes and servers handle requests at the same time, and the
database is the only thing they share. Uniqueness checks, counters and "read, decide,
write" sequences done in Python race each other; locks and constraints only work in the
database.

## 2. Transactions and side effects (tx-)

**Impact:** CRITICAL
**Risk:** correctness
**Description:** Work tied to a transaction must succeed or fail with it. Side effects
that run before the commit survive a rollback; side effects deferred past the commit can
be lost.

## 3. Safe migrations (migration-)

**Impact:** CRITICAL
**Risk:** availability
**Description:** A migration that takes the wrong lock or rewrites a large table can stop
production. The generated SQL, not the migration file, shows what will run.

## 4. Signals (signals-)

**Impact:** HIGH
**Risk:** correctness
**Description:** Signals decouple modules, but receivers run synchronously, inside the
sender's transaction, with no delivery guarantee.

## 5. Queries and N+1 (query-)

**Impact:** HIGH
**Risk:** performance
**Description:** One query per row, duplicated rows from joins and work moved from the
database into Python are the most common causes of slow Django pages.

## 6. Indexes and foreign keys (index-)

**Impact:** HIGH
**Risk:** performance, cost
**Description:** Every index speeds some reads and slows every write. Django creates some
implicitly; each one should be a decision.

## 7. Detection and testing (detect-)

**Impact:** HIGH
**Risk:** all
**Description:** Most rules here fail silently in development. Query counts, captured
on_commit callbacks, EXPLAIN and system checks make them visible.

## 8. Django REST Framework (drf-)

**Impact:** MEDIUM
**Risk:** performance
**Description:** Serializers hide queries and are expensive to build; list endpoints
multiply both.

## 9. Admin at scale (admin-)

**Impact:** MEDIUM
**Risk:** performance
**Description:** The admin's defaults suit small tables; on large ones they run counts,
full scans and one query per row.

## 10. Database operations (ops-)

**Impact:** MEDIUM
**Risk:** availability
**Description:** Timeouts and connection settings decide whether one slow query or
external call takes down the whole application.
