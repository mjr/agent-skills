---
title: Pass values to raw SQL as parameters, never by formatting strings
impact: HIGH
risk: correctness
django: ">=5.2"
database: any
tags: raw-sql, sql-injection, params, rawsql, cursor
sources:
  - https://docs.djangoproject.com/en/stable/topics/db/sql/#passing-parameters-into-raw
  - https://hakibenita.com/django-concurrency
tests: test_query_shapes.py
---

## Pass values to raw SQL as parameters, never by formatting strings

`raw()`, `cursor.execute()`, `RawSQL` and `extra()` run the SQL you give them. A value
interpolated with an f-string, `%` or `.format()` becomes part of the SQL text, so input
containing a quote changes the query: SQL injection.

**Incorrect (the input rewrites the WHERE clause):**

```python
Product.objects.raw(f"SELECT * FROM catalog_product WHERE name = '{name}'")
# name = "x' OR '1'='1" returns every row.
```

**Correct (the driver sends the value separately):**

```python
Product.objects.raw('SELECT * FROM catalog_product WHERE name = %s', [name])

with connection.cursor() as cursor:
    cursor.execute('UPDATE catalog_product SET hits = hits + 1 WHERE id = %s', [pk])
```

Write `%s` without quotes around it; the driver quotes the value. Identifiers (table and
column names) cannot be parameters: build them from model metadata and quote them with
`connection.ops.quote_name()`, never from user input.

**When not to apply:** nothing; even values that "cannot" contain quotes today (IDs,
enum values) should go through parameters.

**How to detect:** f-strings, `%` formatting or `.format()` building strings passed to
`raw(`, `execute(`, `RawSQL(` or `extra(`.

Reference: [Passing parameters into raw()](https://docs.djangoproject.com/en/stable/topics/db/sql/#passing-parameters-into-raw)
