---
title: Load what nested serializers read in the view's get_queryset
impact: HIGH
risk: performance
django: ">=5.2"
database: any
tags: drf, serializers, n+1, select_related, prefetch_related, get_queryset
sources:
  - https://hakibenita.com/django-rest-framework-slow
tests: test_drf.py
---

## Load what nested serializers read in the view's get_queryset

A serializer field with `source='category.name'`, a nested serializer or a
`many=True` relation reads a relation for every object in the list. The serializer does
not load anything itself, so unless the view's queryset does, every row adds queries:
with three such fields, a page of 50 objects runs 151 queries.

**Incorrect (the serializer reads relations the queryset did not load):**

```python
class ProductSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source='category.name')
    author = serializers.CharField(source='created_by.username')
    tags = TagSerializer(many=True)


class ProductList(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

**Correct (the view loads exactly what the serializer reads):**

```python
class ProductList(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return (
            Product.objects
            .select_related('category', 'created_by')
            .prefetch_related('tags')
        )
```

Two queries, whatever the page size. Keep the loading next to the serializer it serves:
when someone adds a nested field, the queryset must change in the same pull request.

**When not to apply:** detail endpoints that serialize one object pay a few extra
queries at most; the rule matters for lists, exports and nested `many=True` fields.

**How to detect:** serializers with dotted `source=`, nested serializers or `many=True`
fields used by views whose queryset lacks `select_related`/`prefetch_related`. Assert
the query count of list endpoints (see `detect-assert-num-queries`).

Reference: [Improve Serialization Performance in Django Rest Framework](https://hakibenita.com/django-rest-framework-slow)
