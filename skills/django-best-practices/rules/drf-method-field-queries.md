---
title: Do not query inside SerializerMethodField; annotate and read the attribute
impact: HIGH
risk: performance
django: ">=5.2"
database: any
tags: drf, serializermethodfield, n+1, annotate
sources:
  - https://hakibenita.com/django-rest-framework-slow
tests: test_drf.py
---

## Do not query inside SerializerMethodField; annotate and read the attribute

A `SerializerMethodField` runs its method once per object. A method that calls `.count()`,
`.exists()`, `.filter()` or `.aggregate()` is one query per row, and no
`select_related` or `prefetch_related` can fix it, because the method builds a new query
each time.

**Incorrect:**

```python
class ProductSerializer(serializers.ModelSerializer):
    orders = serializers.SerializerMethodField()

    def get_orders(self, product):
        return product.order_set.count()
```

**Correct (compute it in the list query and read the value):**

```python
class ProductSerializer(serializers.ModelSerializer):
    orders = serializers.IntegerField(source='orders_n', read_only=True)


class ProductList(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.annotate(orders_n=Count('order'))
```

When the method needs related objects rather than an aggregate, prefetch them in the
view and work on `product.relation.all()` in the method (see
`query-dont-defeat-prefetch`). For several aggregates over different relations, use
subqueries (see `query-annotate-aggregates`).

**When not to apply:** methods that only combine attributes already loaded (formatting,
arithmetic) are fine.

**How to detect:** `get_<field>` methods that call manager or queryset methods; list
endpoints whose query count grows with the page size.

Reference: [Improve Serialization Performance in Django Rest Framework](https://hakibenita.com/django-rest-framework-slow)
