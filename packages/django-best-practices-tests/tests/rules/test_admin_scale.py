"""admin-list-select-related, admin-no-per-row-queries, admin-fk-widgets,
admin-defer-heavy-fields and admin-default-filters."""

import re
from contextlib import contextmanager

import pytest
from django.contrib import admin
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Exists, OuterRef
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import Category, Order, Product

pytestmark = [pytest.mark.django_db]

User = get_user_model()


@pytest.fixture
def superuser():
    return User.objects.create_superuser('admin', 'admin@example.com', 'x')


def make_products(count, users=1):
    authors = [User.objects.get_or_create(username=f'author{i}')[0] for i in range(users)]
    for i in range(count):
        category = Category.objects.create(name=f'c{i}')
        product = Product.objects.create(
            name=f'p{i}', category=category, created_by=authors[i % users], description='x' * 2000
        )
        Order.objects.create(product=product)


@contextmanager
def admin_config(model, **overrides):
    model_admin = site._registry[model]
    original = {name: getattr(model_admin, name) for name in overrides}
    for name, value in overrides.items():
        setattr(model_admin, name, value)
    try:
        yield model_admin
    finally:
        for name, value in original.items():
            setattr(model_admin, name, value)


def changelist_queries(rf, user, model_admin, query_string=''):
    request = rf.get(f'/admin/catalog/product/?{query_string}')
    request.user = user
    with CaptureQueriesContext(connection) as ctx:
        response = model_admin.changelist_view(request)
        response.render()
    return ctx.captured_queries, response


def author_name(obj):
    return obj.created_by.username


author_name.short_description = 'author'


# admin-list-select-related


@pytest.mark.rule('admin-list-select-related')
def test_plain_foreign_keys_in_list_display_are_joined_automatically(rf, superuser):
    make_products(10)
    with admin_config(Product, list_display=('name', 'category')) as model_admin:
        few, _ = changelist_queries(rf, superuser, model_admin)
        make_products(10)
        many, _ = changelist_queries(rf, superuser, model_admin)
    assert len(few) == len(many)


@pytest.mark.rule('admin-list-select-related')
def test_callables_that_read_relations_are_one_query_per_row(rf, superuser):
    make_products(5)
    with admin_config(Product, list_display=('name', author_name)) as model_admin:
        few, _ = changelist_queries(rf, superuser, model_admin)
        make_products(5)
        many, _ = changelist_queries(rf, superuser, model_admin)
    assert len(many) == len(few) + 5


@pytest.mark.rule('admin-list-select-related')
def test_list_select_related_covers_them(rf, superuser):
    make_products(5)
    with admin_config(
        Product, list_display=('name', author_name), list_select_related=('category', 'created_by')
    ) as model_admin:
        few, _ = changelist_queries(rf, superuser, model_admin)
        make_products(5)
        many, _ = changelist_queries(rf, superuser, model_admin)
    assert len(few) == len(many)


# admin-no-per-row-queries


def orders_count(obj):
    return obj.order_set.count()


@admin.display(description='orders', ordering='orders_n')
def orders_annotated(obj):
    return obj.orders_n


class AnnotatedProductAdmin(admin.ModelAdmin):
    list_display = ('name', orders_annotated)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(orders_n=Count('order'))


@pytest.mark.rule('admin-no-per-row-queries')
def test_count_in_list_display_is_one_query_per_row(rf, superuser):
    make_products(5)
    with admin_config(Product, list_display=('name', orders_count)) as model_admin:
        few, _ = changelist_queries(rf, superuser, model_admin)
        make_products(5)
        many, _ = changelist_queries(rf, superuser, model_admin)
    assert len(many) == len(few) + 5


@pytest.mark.rule('admin-no-per-row-queries')
def test_annotating_in_get_queryset_keeps_it_constant(rf, superuser):
    make_products(5)
    model_admin = AnnotatedProductAdmin(Product, site)
    few, _ = changelist_queries(rf, superuser, model_admin)
    make_products(5)
    many, response = changelist_queries(rf, superuser, model_admin)
    assert len(few) == len(many)
    assert 'column-orders_annotated' in response.rendered_content


# admin-fk-widgets


def add_form(rf, user, model_admin):
    request = rf.get('/admin/catalog/product/add/')
    request.user = user
    with CaptureQueriesContext(connection) as ctx:
        response = model_admin.add_view(request)
        response.render()
    html = response.rendered_content
    select = re.search(r'<select name="created_by".*?</select>', html, re.S)
    options = select.group(0).count('<option') if select else 0
    return options, ctx.captured_queries


@pytest.mark.rule('admin-fk-widgets')
def test_default_widget_renders_every_related_row(rf, superuser):
    make_products(1, users=40)
    with admin_config(Product, raw_id_fields=(), autocomplete_fields=()) as model_admin:
        options, queries = add_form(rf, superuser, model_admin)
    assert options >= User.objects.count()
    assert any('FROM "auth_user"' in q['sql'] and 'LIMIT' not in q['sql'] for q in queries)


@pytest.mark.rule('admin-fk-widgets')
@pytest.mark.parametrize('option', ['raw_id_fields', 'autocomplete_fields'])
def test_raw_id_and_autocomplete_render_no_options(rf, superuser, option):
    make_products(1, users=40)
    with admin_config(Product, **{option: ('created_by',)}) as model_admin:
        options, _ = add_form(rf, superuser, model_admin)
    assert options <= 1  # Only an empty or the selected value.


# admin-defer-heavy-fields


class LightProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')

    def get_queryset(self, request):
        return super().get_queryset(request).defer('description')


@pytest.mark.rule('admin-defer-heavy-fields')
def test_changelist_selects_every_column_unless_deferred(rf, superuser):
    make_products(3)
    default, _ = changelist_queries(rf, superuser, site._registry[Product])
    light, _ = changelist_queries(rf, superuser, LightProductAdmin(Product, site))

    def listing(queries):
        return next(q['sql'] for q in queries if q['sql'].startswith('SELECT "catalog_product"."id"'))

    assert '"catalog_product"."description"' in listing(default)
    assert '"catalog_product"."description"' not in listing(light)


# admin-default-filters


class RecentFirstFilter(admin.SimpleListFilter):
    """Defaults to products with orders; 'all' must be chosen explicitly."""

    title = 'orders'
    parameter_name = 'ordered'

    def lookups(self, request, model_admin):
        return [('yes', 'With orders'), ('all', 'All')]

    def choices(self, changelist):
        for value, label in self.lookup_choices:
            yield {
                'selected': (self.value() or 'yes') == value,
                'query_string': changelist.get_query_string({self.parameter_name: value}),
                'display': label,
            }

    def queryset(self, request, queryset):
        if (self.value() or 'yes') == 'yes':
            return queryset.filter(Exists(Order.objects.filter(product=OuterRef('pk'))))
        return queryset


class FilteredProductAdmin(admin.ModelAdmin):
    list_display = ('name',)
    list_filter = (RecentFirstFilter,)


@pytest.mark.rule('admin-default-filters')
def test_list_filter_can_apply_a_default_without_redirects(rf, superuser):
    make_products(3)
    user = User.objects.get(username='author0')
    Product.objects.create(name='never ordered', category=Category.objects.first(), created_by=user)
    model_admin = FilteredProductAdmin(Product, site)

    _, default = changelist_queries(rf, superuser, model_admin)
    _, everything = changelist_queries(rf, superuser, model_admin, 'ordered=all')
    assert 'never ordered' not in default.rendered_content
    assert 'never ordered' in everything.rendered_content


@pytest.mark.rule('admin-list-select-related')
def test_setting_it_replaces_the_automatic_join(rf, superuser):
    make_products(5)
    with admin_config(
        Product, list_display=('name', 'category', author_name), list_select_related=('created_by',)
    ) as model_admin:
        few, _ = changelist_queries(rf, superuser, model_admin)
        make_products(5)
        many, _ = changelist_queries(rf, superuser, model_admin)
    assert len(many) == len(few) + 5  # category is no longer joined.


@pytest.mark.rule('admin-no-per-row-queries')
def test_link_to_a_filtered_changelist_is_accepted(rf, superuser):
    make_products(3)
    product = Product.objects.first()
    request = rf.get(f'/admin/catalog/order/?product__id__exact={product.pk}')
    request.user = superuser
    response = site._registry[Order].changelist_view(request)
    response.render()
    assert response.status_code == 200
    assert response.context_data['cl'].result_count == 1


@pytest.mark.rule('admin-defer-heavy-fields')
def test_change_form_uses_the_same_queryset_and_loads_the_field_lazily(rf, superuser):
    make_products(1)
    product = Product.objects.first()
    model_admin = LightProductAdmin(Product, site)
    request = rf.get(f'/admin/catalog/product/{product.pk}/change/')
    request.user = superuser
    with CaptureQueriesContext(connection) as ctx:
        response = model_admin.change_view(request, str(product.pk))
        response.render()
    assert 'x' * 2000 in response.rendered_content
    assert any('"catalog_product"."description"' in q['sql'] and 'WHERE' in q['sql'] for q in ctx.captured_queries)
