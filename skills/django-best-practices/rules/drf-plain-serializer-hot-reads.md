---
title: Use lighter serialization on hot read-only endpoints
impact: MEDIUM
risk: performance
django: ">=4.2"
database: any
tags: drf, serializer, modelserializer, values, performance
sources:
  - https://hakibenita.com/django-rest-framework-slow
tests: test_drf.py
---

## Use lighter serialization on hot read-only endpoints

Serializers are convenient and expensive: each object goes through every field's
`to_representation`, and a `ModelSerializer` also builds its fields by introspecting the
model, with validators for writable fields. For endpoints that return large lists and
never write (feeds, exports, autocomplete, dashboards), most of that work is unused.
Building plain dictionaries from `.values()` is an order of magnitude cheaper than any
serializer.

**Incorrect (full ModelSerializer machinery to return four columns):**

```python
class UrlSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortUrl
        fields = ['id', 'key', 'target_url', 'hits']
```

**Correct (choose by how hot the endpoint is):**

```python
# A declared, read-only serializer: explicit and still documented by DRF tooling.
class UrlSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    key = serializers.CharField(read_only=True)
    target_url = serializers.CharField(read_only=True)
    hits = serializers.IntegerField(read_only=True)


# For the hottest read paths: skip serializers entirely.
class UrlExport(APIView):
    def get(self, request):
        rows = ShortUrl.objects.values('id', 'key', 'target_url', 'hits')
        return Response(list(rows))
```

Measure before and after on your data; the exact ratios depend on the Django and DRF
versions (old benchmarks from 2019 no longer apply as published), but dictionaries stay
far cheaper than serializers.

**When not to apply:** write endpoints, and read endpoints of normal size, are better
served by the clarity, validation and schema generation of serializers. Bypassing them
also bypasses field-level formatting (dates, decimals) that clients may rely on; keep
the output format identical.

**How to detect:** profile the slowest list endpoints; when serialization dominates
(rather than queries), these endpoints are candidates.

Reference: [Improve Serialization Performance in Django Rest Framework](https://hakibenita.com/django-rest-framework-slow)
