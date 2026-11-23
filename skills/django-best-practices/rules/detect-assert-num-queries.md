---
title: Assert that query counts do not grow with the number of rows
impact: HIGH
risk: performance
django: ">=5.2"
database: any
tags: testing, assertnumqueries, n+1, captureQueriesContext
sources:
  - https://docs.djangoproject.com/en/stable/topics/testing/tools/#django.test.TransactionTestCase.assertNumQueries
tests: test_detect.py
---

## Assert that query counts do not grow with the number of rows

N+1 problems do not fail tests: the page still renders, only slower, and with the two
rows a fixture creates the difference is invisible. A test that pins the number of queries
catches the regression the day someone adds a nested serializer or a template that reads
a relation. The strongest form runs the same code with few and with many rows and
asserts the count is the same.

**Incorrect (a test that only checks the output):**

```python
def test_product_list(client):
    response = client.get('/products/')
    assert response.status_code == 200
```

**Correct (the count is part of the contract):**

```python
def test_product_list_queries_do_not_grow(client, django_assert_num_queries):
    make_products(2)
    with django_assert_num_queries(3):  # session, products, prefetch
        client.get('/products/')

    make_products(20)
    with django_assert_num_queries(3):
        client.get('/products/')
```

With Django's test runner, `self.assertNumQueries(3)` does the same. For a looser check,
`django.test.utils.CaptureQueriesContext` records the queries so the test can compare
counts or inspect the SQL.

**When not to apply:** exact counts make tests brittle when unrelated queries (session,
permissions) change; asserting "same count for 2 and 20 rows" is more robust than a
magic number.

**How to detect:** list and detail views, serializers and admin pages without any
query-count assertion. On Django 6.1+, combine with `FETCH_RAISE` (see
`query-fetch-modes`).

Reference: [assertNumQueries](https://docs.djangoproject.com/en/stable/topics/testing/tools/#django.test.TransactionTestCase.assertNumQueries)
