"""query-exists-over-distinct, query-only-defer, query-limit-in-db,
query-push-work-to-database, query-bulk-writes, query-iterator-large-sets and
query-raw-sql-params."""

import pytest
from django.contrib.auth import get_user_model
from django.db import ProgrammingError, connection
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Extract
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import Category, Job, Product, ShortUrl, Wallet

pytestmark = [pytest.mark.django_db]


def queries(func):
    with CaptureQueriesContext(connection) as ctx:
        result = func()
    return ctx.captured_queries, result


@pytest.fixture
def products():
    user = get_user_model().objects.create_user('author')
    fruit = Category.objects.create(name='fruit')
    nuts = Category.objects.create(name='nuts')
    for name in ('apple', 'apricot', 'avocado'):
        Product.objects.create(name=name, category=fruit, created_by=user, description='x' * 500)
    Product.objects.create(name='almond', category=nuts, created_by=user)
    Product.objects.create(name='walnut', category=nuts, created_by=user)
    return fruit, nuts


# query-exists-over-distinct


@pytest.mark.rule('query-exists-over-distinct')
def test_filtering_across_a_relation_duplicates_rows(products):
    names = list(Category.objects.filter(products__name__startswith='a').values_list('name', flat=True))
    assert sorted(names) == ['fruit', 'fruit', 'fruit', 'nuts']


@pytest.mark.rule('query-exists-over-distinct')
def test_distinct_on_requires_matching_order(products):
    with pytest.raises(ProgrammingError, match='SELECT DISTINCT ON expressions must match'):
        list(Category.objects.filter(products__name__startswith='a').distinct('id').order_by('name'))


@pytest.mark.rule('query-exists-over-distinct')
def test_exists_filters_without_duplicates_or_ordering_limits(products):
    matching = Product.objects.filter(category=OuterRef('pk'), name__startswith='a')
    captured, names = queries(
        lambda: list(
            Category.objects.filter(Exists(matching)).order_by('-name').values_list('name', flat=True)
        )
    )
    assert names == ['nuts', 'fruit']
    assert 'EXISTS' in captured[0]['sql'] and 'DISTINCT' not in captured[0]['sql']


# query-only-defer


@pytest.mark.rule('query-only-defer')
def test_reading_a_deferred_field_is_one_query_per_row(products):
    captured, rows = queries(lambda: [p.description for p in Product.objects.only('name')])
    assert len(captured) == 1 + len(rows)


@pytest.mark.rule('query-only-defer')
def test_values_returns_just_the_columns_asked_for(products):
    captured, rows = queries(lambda: list(Product.objects.values('name', 'category__name')))
    assert len(captured) == 1
    assert '"description"' not in captured[0]['sql']
    assert set(rows[0]) == {'name', 'category__name'}


# query-limit-in-db


@pytest.mark.rule('query-limit-in-db')
def test_slicing_a_list_loads_every_row(products):
    captured, _ = queries(lambda: list(Product.objects.all())[:2])
    assert 'LIMIT' not in captured[0]['sql']


@pytest.mark.rule('query-limit-in-db')
def test_slicing_the_queryset_adds_a_limit(products):
    captured, _ = queries(lambda: list(Product.objects.all()[:2]))
    assert 'LIMIT 2' in captured[0]['sql']


@pytest.mark.rule('query-limit-in-db')
def test_len_and_bool_fetch_rows_count_and_exists_do_not(products):
    assert 'COUNT(*)' not in queries(lambda: len(Product.objects.all()))[0][0]['sql']
    assert 'COUNT(*)' in queries(lambda: Product.objects.count())[0][0]['sql']
    assert 'LIMIT 1' not in queries(lambda: bool(Product.objects.all()))[0][0]['sql']
    assert 'LIMIT 1' in queries(lambda: Product.objects.exists())[0][0]['sql']


@pytest.mark.rule('query-limit-in-db')
def test_limit_plus_one_detects_truncation_without_a_count(products):
    limit = 3
    captured, rows = queries(lambda: list(Product.objects.order_by('pk')[: limit + 1]))
    assert len(captured) == 1
    assert len(rows) > limit  # More rows exist than the page shows.


# query-push-work-to-database


@pytest.mark.rule('query-push-work-to-database')
def test_conditional_aggregates_in_one_query(products):
    captured, totals = queries(
        lambda: Product.objects.aggregate(
            total=Count('pk'),
            fruit=Count('pk', filter=Q(category__name='fruit')),
        )
    )
    assert len(captured) == 1
    assert totals == {'total': 5, 'fruit': 3}
    assert 'FILTER (WHERE' in captured[0]['sql']


@pytest.mark.rule('query-push-work-to-database')
def test_extract_epoch_works_on_durations():
    from datetime import timedelta

    from labs.catalog.models import Payment

    Payment.objects.create()
    queryset = Payment.objects.annotate(seconds=Extract(timedelta(minutes=2) - timedelta(seconds=30), 'epoch'))
    assert 'EXTRACT(EPOCH FROM' in str(queryset.query)


@pytest.mark.rule('query-push-work-to-database')
def test_summing_in_python_loads_every_row():
    Wallet.objects.bulk_create(Wallet(balance=b) for b in range(50))
    python_side, total_py = queries(lambda: sum(w.balance for w in Wallet.objects.all()))
    db_side, total_db = queries(lambda: Wallet.objects.aggregate(s=Sum('balance'))['s'])
    assert total_py == total_db
    assert 'SUM(' in db_side[0]['sql'] and 'SUM(' not in python_side[0]['sql']


# query-bulk-writes


@pytest.mark.rule('query-bulk-writes')
def test_create_in_a_loop_is_one_insert_per_row():
    captured, _ = queries(lambda: [Job.objects.create() for _ in range(20)])
    assert len(captured) == 20


@pytest.mark.rule('query-bulk-writes')
def test_bulk_create_is_one_insert_per_batch():
    captured, _ = queries(lambda: Job.objects.bulk_create([Job() for _ in range(20)], batch_size=10))
    assert len(captured) == 2


@pytest.mark.rule('query-bulk-writes')
def test_bulk_create_can_upsert_on_a_unique_field():
    ShortUrl.objects.create(key='k', target_url='https://old.example')
    ShortUrl.objects.bulk_create(
        [ShortUrl(key='k', target_url='https://new.example'), ShortUrl(key='n', target_url='https://n.example')],
        update_conflicts=True,
        unique_fields=['key'],
        update_fields=['target_url'],
    )
    assert ShortUrl.objects.get(key='k').target_url == 'https://new.example'
    assert ShortUrl.objects.count() == 2


# query-iterator-large-sets


@pytest.mark.rule('query-iterator-large-sets')
def test_iterator_keeps_no_result_cache(products):
    queryset = Product.objects.all()
    list(queryset.iterator(chunk_size=2))
    assert queryset._result_cache is None
    list(queryset)
    assert queryset._result_cache is not None


@pytest.mark.rule('query-iterator-large-sets')
def test_iterator_with_chunk_size_still_prefetches(products):
    captured, _ = queries(
        lambda: [p.tags.all()[:] for p in Product.objects.prefetch_related('tags').iterator(chunk_size=2)]
    )
    # PostgreSQL streams the rows through a server-side cursor (one DECLARE), and the
    # prefetch runs once per chunk: 5 products in chunks of 2 means 3 prefetch queries.
    assert captured[0]['sql'].startswith('DECLARE')
    assert len(captured) == 1 + 3


# query-raw-sql-params


@pytest.mark.rule('query-raw-sql-params')
def test_formatting_values_into_sql_is_injectable(products):
    user_input = "x' OR '1'='1"
    rows = list(Product.objects.raw(f"SELECT * FROM catalog_product WHERE name = '{user_input}'"))
    assert len(rows) == 5  # Every row: the input became SQL.


@pytest.mark.rule('query-raw-sql-params')
def test_parameters_keep_values_as_values(products):
    user_input = "x' OR '1'='1"
    rows = list(Product.objects.raw('SELECT * FROM catalog_product WHERE name = %s', [user_input]))
    assert rows == []
