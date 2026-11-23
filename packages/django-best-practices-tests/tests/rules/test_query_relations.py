"""query-select-related, query-prefetch-related, query-prefetch-object,
query-dont-defeat-prefetch, query-fetch-modes and query-annotate-aggregates."""

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldError
from django.db import connection
from django.db.models import Count, OuterRef, Prefetch, Subquery
from django.db.models.functions import Coalesce
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import Category, Order, Product, Tag

pytestmark = [pytest.mark.django_db]

needs_fetch_modes = pytest.mark.skipif(django.VERSION < (6, 1), reason='fetch modes are new in 6.1')


@pytest.fixture
def catalog():
    users = [get_user_model().objects.create_user(f'user{i}') for i in range(3)]
    tags = [Tag.objects.create(name=n) for n in ('apple', 'avocado', 'berry')]
    categories = []
    for c in range(3):
        category = Category.objects.create(name=f'category {c}')
        categories.append(category)
        for p in range(4):
            product = Product.objects.create(
                name=f'product {c}.{p}', category=category, created_by=users[p % 3]
            )
            product.tags.set(tags[: (p % 3) + 1])
            for _ in range(p):
                Order.objects.create(product=product)
    return categories


def queries(func):
    with CaptureQueriesContext(connection) as ctx:
        result = func()
    return len(ctx.captured_queries), result


# query-select-related


@pytest.mark.rule('query-select-related')
def test_forward_foreign_key_in_a_loop_is_one_query_per_row(catalog):
    count, names = queries(lambda: [p.category.name for p in Product.objects.all()])
    assert count == 1 + len(names)


@pytest.mark.rule('query-select-related')
def test_select_related_joins_it_in_one_query(catalog):
    count, _ = queries(
        lambda: [(p.category.name, p.created_by.username) for p in Product.objects.select_related('category', 'created_by')]
    )
    assert count == 1


@pytest.mark.rule('query-select-related')
def test_select_related_cannot_follow_many_to_many(catalog):
    with pytest.raises(FieldError):
        list(Product.objects.select_related('tags'))


# query-prefetch-related


@pytest.mark.rule('query-prefetch-related')
def test_many_to_many_in_a_loop_is_one_query_per_row(catalog):
    count, rows = queries(lambda: [[t.name for t in p.tags.all()] for p in Product.objects.all()])
    assert count == 1 + len(rows)


@pytest.mark.rule('query-prefetch-related')
def test_prefetch_related_is_one_query_per_relation(catalog):
    count, _ = queries(
        lambda: [
            ([t.name for t in p.tags.all()], [o.pk for o in p.order_set.all()])
            for p in Product.objects.prefetch_related('tags', 'order_set')
        ]
    )
    assert count == 3


# query-prefetch-object


@pytest.mark.rule('query-prefetch-object')
def test_prefetch_with_a_queryset_joins_the_next_level(catalog):
    def chained():
        return [
            [p.created_by.username for p in c.products.all()]
            for c in Category.objects.prefetch_related('products__created_by')
        ]

    def with_queryset():
        products = Prefetch('products', queryset=Product.objects.select_related('created_by'))
        return [
            [p.created_by.username for p in c.products.all()]
            for c in Category.objects.prefetch_related(products)
        ]

    assert queries(chained)[0] == 3
    assert queries(with_queryset)[0] == 2


@pytest.mark.rule('query-prefetch-object')
def test_to_attr_holds_a_filtered_list_and_leaves_the_relation_intact(catalog):
    a_tags = Prefetch('tags', queryset=Tag.objects.filter(name__startswith='a'), to_attr='a_tags')
    product = Product.objects.prefetch_related(a_tags).get(name='product 0.2')
    assert isinstance(product.a_tags, list)
    assert {t.name for t in product.a_tags} == {'apple', 'avocado'}
    assert product.tags.count() == 3  # The full relation, from a new query.


@pytest.mark.rule('query-prefetch-object')
def test_filtered_prefetch_without_to_attr_replaces_the_relation_cache(catalog):
    a_tags = Prefetch('tags', queryset=Tag.objects.filter(name__startswith='a'))
    product = Product.objects.prefetch_related(a_tags).get(name='product 0.2')
    # Any code reading product.tags.all() now sees only the filtered tags.
    assert {t.name for t in product.tags.all()} == {'apple', 'avocado'}


@pytest.mark.rule('query-prefetch-object')
@pytest.mark.parametrize('taken', ['name', 'category', 'order_set'])
def test_to_attr_that_reuses_a_name_silently_loses_the_prefetch(catalog, taken):
    product = Product.objects.prefetch_related(Prefetch('tags', to_attr=taken)).get(
        name='product 0.2'
    )
    assert not isinstance(getattr(product, taken), list)  # No error, and no tags either.


# query-dont-defeat-prefetch


@pytest.mark.rule('query-dont-defeat-prefetch')
@pytest.mark.parametrize(
    'use, extra_queries',
    [
        (lambda p: list(p.tags.all()), 0),
        (lambda p: p.tags.count(), 0),
        (lambda p: [t for t in p.tags.all() if t.name.startswith('a')], 0),
        (lambda p: list(p.tags.filter(name__startswith='a')), 1),
        (lambda p: list(p.tags.order_by('name')), 1),
        (lambda p: list(p.tags.values_list('name', flat=True)), 1),
        (lambda p: p.tags.first(), 1),
        (lambda p: p.tags.exists(), 0),
    ],
)
def test_only_plain_access_uses_the_prefetched_rows(catalog, use, extra_queries):
    products = list(Product.objects.prefetch_related('tags'))
    count, _ = queries(lambda: [use(p) for p in products])
    assert count == extra_queries * len(products)


# query-fetch-modes (Django 6.1+)


@needs_fetch_modes
@pytest.mark.rule('query-fetch-modes')
def test_fetch_peers_loads_the_relation_for_all_rows_at_first_access(catalog):
    from django.db.models import FETCH_PEERS

    count, _ = queries(lambda: [p.category.name for p in Product.objects.fetch_mode(FETCH_PEERS)])
    assert count == 2


@needs_fetch_modes
@pytest.mark.rule('query-fetch-modes')
def test_fetch_peers_also_batches_deferred_fields(catalog):
    from django.db.models import FETCH_PEERS

    count, _ = queries(
        lambda: [p.description for p in Product.objects.only('name').fetch_mode(FETCH_PEERS)]
    )
    assert count == 2


@needs_fetch_modes
@pytest.mark.rule('query-fetch-modes')
def test_fetch_raise_turns_a_lazy_query_into_an_error(catalog):
    from django.core.exceptions import FieldFetchBlocked
    from django.db.models import FETCH_RAISE

    product = Product.objects.fetch_mode(FETCH_RAISE).first()
    with pytest.raises(FieldFetchBlocked):
        product.category
    with pytest.raises(FieldFetchBlocked):
        Product.objects.only('name').fetch_mode(FETCH_RAISE).first().description


@needs_fetch_modes
@pytest.mark.rule('query-fetch-modes')
def test_fetch_modes_do_not_cover_reverse_and_many_to_many_managers(catalog):
    from django.db.models import FETCH_RAISE

    products = list(Product.objects.fetch_mode(FETCH_RAISE))
    count, _ = queries(lambda: [list(p.tags.all()) for p in products])
    assert count == len(products)  # Still one query per row: use prefetch_related.


# query-annotate-aggregates


@pytest.mark.rule('query-annotate-aggregates')
def test_count_per_row_is_one_query_per_row(catalog):
    count, rows = queries(lambda: [p.order_set.count() for p in Product.objects.all()])
    assert count == 1 + len(rows)


@pytest.mark.rule('query-annotate-aggregates')
def test_annotate_counts_in_the_same_query(catalog):
    count, rows = queries(lambda: list(Product.objects.annotate(orders=Count('order'))))
    assert count == 1
    assert sorted(p.orders for p in rows) == sorted([0, 1, 2, 3] * 3)


@pytest.mark.rule('query-annotate-aggregates')
def test_two_counts_over_different_relations_multiply_each_other(catalog):
    product = Product.objects.annotate(tags_n=Count('tags'), orders_n=Count('order')).get(
        name='product 0.2'
    )  # Really 3 tags and 2 orders.
    assert (product.tags_n, product.orders_n) == (6, 6)

    fixed = Product.objects.annotate(
        tags_n=Count('tags', distinct=True), orders_n=Count('order', distinct=True)
    ).get(name='product 0.2')
    assert (fixed.tags_n, fixed.orders_n) == (3, 2)


@pytest.mark.rule('query-annotate-aggregates')
def test_subquery_count_avoids_the_join_entirely(catalog):
    orders = (
        Order.objects.filter(product=OuterRef('pk'))
        .order_by()
        .values('product')
        .annotate(n=Count('pk'))
        .values('n')
    )
    product = (
        Product.objects.annotate(tags_n=Count('tags'), orders_n=Coalesce(Subquery(orders), 0))
        .get(name='product 0.2')
    )
    assert (product.tags_n, product.orders_n) == (3, 2)
