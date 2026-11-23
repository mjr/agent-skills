---
title: Mark fields that are never written as read-only
impact: LOW-MEDIUM
risk: performance
django: ">=5.2"
database: any
tags: drf, read_only_fields, validators, uniquevalidator
sources:
  - https://hakibenita.com/django-rest-framework-slow
tests: test_drf.py
---

## Mark fields that are never written as read-only

A `ModelSerializer` treats every field as writable unless told otherwise. Writable
fields get validators, and a model field with `unique=True` gets a `UniqueValidator`
that queries the database on every validation. Marking fields as read-only removes that
work and documents which fields the endpoint accepts.

**Incorrect (all fields writable by default):**

```python
class UrlSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortUrl
        fields = ['key', 'target_url', 'hits']
```

**Correct:**

```python
class UrlSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortUrl
        fields = ['key', 'target_url', 'hits']
        read_only_fields = ['key', 'hits']
```

`read_only_fields` only applies to fields generated from the model. A field declared
explicitly on the serializer ignores it and needs `read_only=True` itself:

```python
class UrlSerializer(serializers.ModelSerializer):
    key = serializers.CharField(read_only=True)  # read_only_fields would not apply here.
```

A system check can require every `ModelSerializer` to declare `read_only_fields` (see
`detect-system-checks`).

**When not to apply:** a serializer used for writes needs its writable fields writable.
Do not mark everything read-only on a serializer that also creates objects.

**How to detect:** `ModelSerializer` classes without `read_only_fields` used by read-only
views; declared fields listed in `read_only_fields` without `read_only=True`.

Reference: [Improve Serialization Performance in Django Rest Framework](https://hakibenita.com/django-rest-framework-slow)
