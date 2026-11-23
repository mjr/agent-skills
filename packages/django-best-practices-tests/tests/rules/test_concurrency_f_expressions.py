"""concurrency-f-expressions.

What the attribute holds after saving an F() expression changed in Django 6.0: 5.2 keeps
the expression, 6.0+ reads the new value back with RETURNING. Both versions have a trap
when the same instance is saved again.
"""

import django
import pytest
from django.db import connection
from django.db.models import F
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import ShortUrl
from tests.helpers import Session

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('concurrency-f-expressions')]


@pytest.fixture
def url():
    return ShortUrl.objects.create(key='k', target_url='https://a.example')


def increment_in_python(pk):
    obj = ShortUrl.objects.get(pk=pk)
    obj.hits += 1
    obj.save(update_fields=['hits'])


def test_read_modify_write_loses_an_increment(url):
    mine = ShortUrl.objects.get(pk=url.pk)  # Both requests read hits=0 ...
    with Session() as other:
        other.run(lambda conn: increment_in_python(url.pk))  # ... the other writes 1 ...
    mine.hits += 1
    mine.save(update_fields=['hits'])  # ... and this one writes 1 again.

    url.refresh_from_db()
    assert url.hits == 1


def test_f_expression_keeps_both_increments(url):
    mine = ShortUrl.objects.get(pk=url.pk)
    with Session() as other:
        other.run(lambda conn: ShortUrl.objects.filter(pk=url.pk).update(hits=F('hits') + 1))
    mine.hits = F('hits') + 1
    mine.save(update_fields=['hits'])

    url.refresh_from_db()
    assert url.hits == 2


@pytest.mark.skipif(django.VERSION >= (6, 0), reason='Django 6.0+ refreshes the attribute')
def test_before_6_0_a_second_save_applies_the_increment_again(url):
    url.hits = F('hits') + 1
    url.save(update_fields=['hits'])
    assert not isinstance(url.hits, int)  # Still the expression.

    url.save(update_fields=['hits'])  # Re-applies "hits + 1".
    url.refresh_from_db(fields=['hits'])
    assert url.hits == 2


@pytest.mark.skipif(django.VERSION < (6, 0), reason='Django 6.0 added RETURNING on save')
def test_from_6_0_the_value_is_read_back_and_a_second_save_overwrites(url):
    url.hits = F('hits') + 1
    with CaptureQueriesContext(connection) as ctx:
        url.save(update_fields=['hits'])
    assert 'RETURNING' in ctx.captured_queries[0]['sql']
    assert url.hits == 1  # A plain int again.

    with Session() as other:  # Another request increments meanwhile ...
        other.run(lambda conn: ShortUrl.objects.filter(pk=url.pk).update(hits=F('hits') + 1))
    url.save(update_fields=['hits'])  # ... and this writes the literal 1 back.

    url.refresh_from_db(fields=['hits'])
    assert url.hits == 1


def test_queryset_update_is_a_single_query(url):
    with CaptureQueriesContext(connection) as ctx:
        ShortUrl.objects.filter(pk=url.pk).update(hits=F('hits') + 1)
    assert len(ctx.captured_queries) == 1
    assert '"hits" = ("catalog_shorturl"."hits" + 1)' in ctx.captured_queries[0]['sql']
