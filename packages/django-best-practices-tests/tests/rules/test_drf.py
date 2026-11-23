"""drf- rules."""

import time

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext
from rest_framework import generics, pagination, serializers
from rest_framework.test import APIRequestFactory

from labs.catalog.models import Category, Order, Product, ShortUrl, Tag

pytestmark = [pytest.mark.django_db]

User = get_user_model()


@pytest.fixture
def catalog():
    user = User.objects.create_user('author')
    tags = [Tag.objects.create(name=n) for n in ('red', 'green')]
    for i in range(10):
        category = Category.objects.create(name=f'c{i}')
        product = Product.objects.create(name=f'p{i}', category=category, created_by=user)
        product.tags.set(tags)
        Order.objects.create(product=product)


def call(view, path='/products/'):
    request = APIRequestFactory().get(path)
    with CaptureQueriesContext(connection) as ctx:
        response = view(request)
        response.render()
    return response, ctx.captured_queries


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name']


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source='category.name')
    author = serializers.CharField(source='created_by.username')
    tags = TagSerializer(many=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'category', 'author', 'tags']


# drf-queryset-for-nested


@pytest.mark.rule('drf-queryset-for-nested')
def test_nested_serializer_on_a_plain_queryset_is_n_plus_one(catalog):
    view = generics.ListAPIView.as_view(queryset=Product.objects.all(), serializer_class=ProductSerializer)
    response, queries = call(view)
    assert len(response.data) == 10
    assert len(queries) == 1 + 10 * 3  # category, author and tags for every product.


@pytest.mark.rule('drf-queryset-for-nested')
def test_get_queryset_with_select_and_prefetch_is_constant(catalog):
    class ProductList(generics.ListAPIView):
        serializer_class = ProductSerializer

        def get_queryset(self):
            return Product.objects.select_related('category', 'created_by').prefetch_related('tags')

    _, queries = call(ProductList.as_view())
    assert len(queries) == 2


# drf-method-field-queries


class OrderCountByMethod(serializers.ModelSerializer):
    orders = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'orders']

    def get_orders(self, product):
        return product.order_set.count()


class OrderCountByAnnotation(serializers.ModelSerializer):
    orders = serializers.IntegerField(source='orders_n', read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'orders']


@pytest.mark.rule('drf-method-field-queries')
def test_method_field_that_queries_runs_once_per_row(catalog):
    view = generics.ListAPIView.as_view(queryset=Product.objects.all(), serializer_class=OrderCountByMethod)
    _, queries = call(view)
    assert len(queries) == 1 + 10


@pytest.mark.rule('drf-method-field-queries')
def test_annotated_value_comes_with_the_list_query(catalog):
    view = generics.ListAPIView.as_view(
        queryset=Product.objects.annotate(orders_n=Count('order')), serializer_class=OrderCountByAnnotation
    )
    response, queries = call(view)
    assert len(queries) == 1
    assert {row['orders'] for row in response.data} == {1}


# drf-plain-serializer-hot-reads


class UrlModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortUrl
        fields = ['id', 'key', 'target_url', 'hits']


class UrlPlainSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    key = serializers.CharField(read_only=True)
    target_url = serializers.CharField(read_only=True)
    hits = serializers.IntegerField(read_only=True)


def best_of(func, repeat=5):
    timings = []
    for _ in range(repeat):
        start = time.perf_counter()
        func()
        timings.append(time.perf_counter() - start)
    return min(timings)


@pytest.mark.rule('drf-plain-serializer-hot-reads')
def test_serializer_cost_compared_with_plain_dictionaries():
    ShortUrl.objects.bulk_create(ShortUrl(key=f'k{i}', target_url='https://a.example') for i in range(2000))
    urls = list(ShortUrl.objects.all())
    rows = list(ShortUrl.objects.values('id', 'key', 'target_url', 'hits'))

    model = best_of(lambda: UrlModelSerializer(urls, many=True).data)
    plain = best_of(lambda: UrlPlainSerializer(urls, many=True).data)
    dicts = best_of(lambda: [dict(r) for r in rows])

    # Orders of magnitude, not exact numbers: dictionaries are far cheaper than any
    # serializer, and a ModelSerializer is not cheaper than a declared one.
    assert dicts * 10 < plain
    assert plain <= model * 1.5


# drf-read-only-fields


class UrlWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortUrl
        fields = ['key', 'target_url']


class UrlReadOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortUrl
        fields = ['key', 'target_url']
        read_only_fields = fields


@pytest.mark.rule('drf-read-only-fields')
def test_writable_unique_field_gets_a_validator_that_queries():
    serializer = UrlWriteSerializer(data={'key': 'k', 'target_url': 'https://a.example'})
    with CaptureQueriesContext(connection) as ctx:
        assert serializer.is_valid()
    assert any('"catalog_shorturl"."key"' in q['sql'] for q in ctx.captured_queries)


@pytest.mark.rule('drf-read-only-fields')
def test_read_only_fields_drop_the_validators():
    from rest_framework.validators import UniqueValidator

    writable = UrlWriteSerializer().fields['key'].validators
    read_only = UrlReadOnlySerializer().fields
    assert any(isinstance(v, UniqueValidator) for v in writable)
    assert all(field.read_only for field in read_only.values())
    assert not any(isinstance(v, UniqueValidator) for v in read_only['key'].validators)


@pytest.mark.rule('drf-read-only-fields')
def test_read_only_fields_ignores_explicitly_declared_fields():
    class Declared(serializers.ModelSerializer):
        key = serializers.CharField()

        class Meta:
            model = ShortUrl
            fields = ['key', 'target_url']
            read_only_fields = ['key', 'target_url']

    fields = Declared().fields
    assert fields['target_url'].read_only
    assert not fields['key'].read_only  # Declared fields must set read_only themselves.


# drf-pagination-count


class PageNumber(pagination.PageNumberPagination):
    page_size = 5


class Cursor(pagination.CursorPagination):
    page_size = 5
    ordering = '-id'


class UrlList(generics.ListAPIView):
    queryset = ShortUrl.objects.order_by('id')
    serializer_class = UrlPlainSerializer


@pytest.mark.rule('drf-pagination-count')
def test_page_number_pagination_counts_the_whole_table_on_every_request():
    ShortUrl.objects.bulk_create(ShortUrl(key=f'k{i}', target_url='https://a.example') for i in range(12))
    response, queries = call(UrlList.as_view(pagination_class=PageNumber), '/urls/?page=2')
    assert response.data['count'] == 12
    assert any('COUNT(*)' in q['sql'] for q in queries)


@pytest.mark.rule('drf-pagination-count')
def test_cursor_pagination_does_not_count():
    ShortUrl.objects.bulk_create(ShortUrl(key=f'k{i}', target_url='https://a.example') for i in range(12))
    response, queries = call(UrlList.as_view(pagination_class=Cursor), '/urls/')
    assert len(response.data['results']) == 5
    assert response.data['next']
    assert not any('COUNT(*)' in q['sql'] for q in queries)


@pytest.mark.rule('drf-pagination-count')
def test_without_a_pagination_class_the_whole_table_is_returned():
    ShortUrl.objects.bulk_create(ShortUrl(key=f'k{i}', target_url='https://a.example') for i in range(12))
    response, queries = call(UrlList.as_view(pagination_class=None), '/urls/')
    assert len(response.data) == 12
    assert 'LIMIT' not in queries[0]['sql']


@pytest.mark.rule('drf-pagination-count')
def test_paginating_an_unordered_queryset_warns():
    from django.core.paginator import UnorderedObjectListWarning

    ShortUrl.objects.bulk_create(ShortUrl(key=f'k{i}', target_url='https://a.example') for i in range(12))
    view = generics.ListAPIView.as_view(
        queryset=ShortUrl.objects.all(), serializer_class=UrlPlainSerializer, pagination_class=PageNumber
    )
    with pytest.warns(UnorderedObjectListWarning):
        call(view, '/urls/?page=2')
