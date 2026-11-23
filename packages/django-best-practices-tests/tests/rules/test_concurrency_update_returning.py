"""concurrency-update-returning."""

import django
import pytest
from django.db import connection
from django.db.models import F
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import ShortUrl

pytestmark = [pytest.mark.django_db, pytest.mark.rule('concurrency-update-returning')]


def resolve_with_returning(key):
    table = connection.ops.quote_name(ShortUrl._meta.db_table)
    rows = list(
        ShortUrl.objects.raw(f'UPDATE {table} SET hits = hits + 1 WHERE key = %s RETURNING *', [key])
    )
    if not rows:
        raise ShortUrl.DoesNotExist(key)
    return rows[0]


def test_one_round_trip_returns_the_new_value():
    ShortUrl.objects.create(key='k', target_url='https://a.example', hits=4)
    with CaptureQueriesContext(connection) as ctx:
        url = resolve_with_returning('k')
    assert len(ctx.captured_queries) == 1
    assert url.hits == 5


def test_orm_needs_a_read_first_and_a_refresh_before_6_0():
    ShortUrl.objects.create(key='k', target_url='https://a.example', hits=4)
    with CaptureQueriesContext(connection) as ctx:
        url = ShortUrl.objects.get(key='k')
        url.hits = F('hits') + 1
        url.save(update_fields=['hits'])
        if django.VERSION < (6, 0):
            url.refresh_from_db(fields=['hits'])
    # 6.0+ reads the value back with RETURNING; 5.2 needs an explicit refresh.
    assert len(ctx.captured_queries) == (2 if django.VERSION >= (6, 0) else 3)
    assert url.hits == 5


def test_missing_key_is_reported():
    with pytest.raises(ShortUrl.DoesNotExist):
        resolve_with_returning('missing')
