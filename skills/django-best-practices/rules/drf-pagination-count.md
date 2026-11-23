---
title: Paginate every list, order it, and know what the page count costs
impact: MEDIUM
risk: performance
django: ">=4.2"
database: any
tags: drf, pagination, count, cursorpagination, ordering
sources:
  - https://www.django-rest-framework.org/api-guide/pagination/
tests: test_drf.py
---

## Paginate every list, order it, and know what the page count costs

Without a pagination class, a list endpoint returns the whole table on every request.
With `PageNumberPagination` or `LimitOffsetPagination`, every request also runs a
`COUNT(*)` over the full filtered queryset to report the total, which on large tables can
cost more than the page itself, and large offsets make PostgreSQL read and discard every
skipped row. `CursorPagination` runs no count and seeks directly to the next page.

**Incorrect (no limit, or a count and offset on a huge table):**

```python
class EventList(generics.ListAPIView):
    queryset = Event.objects.all()          # Unordered, and every row on each request.
    serializer_class = EventSerializer
    pagination_class = None
```

**Correct (bounded, ordered, no count for feeds):**

```python
class EventCursor(pagination.CursorPagination):
    page_size = 50
    ordering = '-id'  # A unique, indexed ordering.


class EventList(generics.ListAPIView):
    queryset = Event.objects.order_by('-id')
    serializer_class = EventSerializer
    pagination_class = EventCursor
```

Set a default `PAGE_SIZE` and `DEFAULT_PAGINATION_CLASS` in `REST_FRAMEWORK` so new
endpoints are paginated by default. Always paginate an ordered queryset: paging an
unordered one makes rows repeat or disappear between pages (Django warns with
`UnorderedObjectListWarning`).

**When not to apply:** when clients need a total count or random page access (admin-like
tables), keep page-number pagination and make the count cheap (filters on indexed
columns), or cache it. Cursor pagination needs a stable, unique ordering.

**How to detect:** list views with `pagination_class = None` or no default pagination;
`COUNT(*)` queries dominating list endpoints in the database statistics;
`UnorderedObjectListWarning` in logs or test output.

Reference: [DRF pagination](https://www.django-rest-framework.org/api-guide/pagination/)
