"""detect- rules."""

import ast
import inspect
import logging
import textwrap
from functools import partial

import pytest
from django.apps import AppConfig
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import checks
from django.db import NotSupportedError, connection, models, transaction
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteWrapper
from django.test import override_settings
from django.test.utils import CaptureQueriesContext, isolate_apps

from labs.catalog.models import Category, Product

User = get_user_model()


def make_products(count):
    user = User.objects.get_or_create(username='author')[0]
    for i in range(count):
        category = Category.objects.create(name=f'c{i}')
        Product.objects.create(name=f'p{i}', category=category, created_by=user)


def product_list(queryset):
    return [(p.name, p.category.name) for p in queryset]


# detect-assert-num-queries


@pytest.mark.django_db
@pytest.mark.rule('detect-assert-num-queries')
def test_query_count_must_not_grow_with_the_rows():
    def count_for(rows, queryset_factory):
        Product.objects.all().delete()
        make_products(rows)
        with CaptureQueriesContext(connection) as ctx:
            product_list(queryset_factory())
        return len(ctx.captured_queries)

    naive = Product.objects.all
    fixed = partial(Product.objects.select_related, 'category')
    assert count_for(2, naive) != count_for(10, naive)  # Grows: N+1.
    assert count_for(2, fixed) == count_for(10, fixed) == 1


@pytest.mark.django_db
@pytest.mark.rule('detect-assert-num-queries')
def test_django_assert_num_queries_fails_on_a_regression(django_assert_num_queries):
    make_products(3)
    with pytest.raises(pytest.fail.Exception):
        with django_assert_num_queries(1):
            product_list(Product.objects.all())


# detect-capture-on-commit


@pytest.mark.django_db  # TestCase-style: the test runs inside a transaction.
@pytest.mark.rule('detect-capture-on-commit')
def test_on_commit_callbacks_never_run_in_a_transactional_test():
    ran = []
    with transaction.atomic():
        transaction.on_commit(lambda: ran.append('callback'))
    assert ran == []  # The outer test transaction never commits.


@pytest.mark.django_db
@pytest.mark.rule('detect-capture-on-commit')
def test_capturing_runs_them(django_capture_on_commit_callbacks):
    ran = []
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with transaction.atomic():
            transaction.on_commit(lambda: ran.append('callback'))
    assert ran == ['callback']
    assert len(callbacks) == 1


# detect-explain


@pytest.mark.django_db
@pytest.mark.rule('detect-explain')
def test_explain_analyze_runs_the_query_and_reports_timing():
    make_products(3)
    plan = Product.objects.filter(name='p1').explain(analyze=True, buffers=True)
    assert 'actual time=' in plan
    assert 'Execution Time' in plan


# detect-sql-logging


@pytest.mark.django_db
@pytest.mark.rule('detect-sql-logging')
def test_sql_is_logged_only_when_debug_is_on(caplog):
    with caplog.at_level(logging.DEBUG, logger='django.db.backends'):
        list(Product.objects.all())
    assert not any('catalog_product' in r.getMessage() for r in caplog.records)

    caplog.clear()
    with override_settings(DEBUG=True), caplog.at_level(logging.DEBUG, logger='django.db.backends'):
        list(Product.objects.all())
    assert any('catalog_product' in r.getMessage() for r in caplog.records)


# detect-test-against-production-engine


def sqlite():
    return SQLiteWrapper({**connection.settings_dict, 'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'})


@pytest.mark.django_db  # Compiling for PostgreSQL reads the server version.
@pytest.mark.rule('detect-test-against-production-engine')
def test_sqlite_silently_drops_select_for_update():
    queryset = Product.objects.select_for_update(of=('self',))
    pg_sql, _ = queryset.query.get_compiler(connection=connection).as_sql()
    sqlite_sql, _ = queryset.query.get_compiler(connection=sqlite()).as_sql()
    assert 'FOR UPDATE' in pg_sql
    assert 'FOR UPDATE' not in sqlite_sql  # No lock, no error: concurrency tests pass for nothing.


@pytest.mark.rule('detect-test-against-production-engine')
def test_sqlite_rejects_postgresql_features():
    queryset = Product.objects.distinct('category')
    with pytest.raises(NotSupportedError):
        queryset.query.get_compiler(connection=sqlite()).as_sql()


# detect-system-checks: the example check from the rule, applied to test models.


def foreign_keys_without_explicit_db_index(model):
    """Return the names of ForeignKey fields declared without db_index (rule example)."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(model)))
    except (OSError, TypeError):
        return []
    missing = []
    for node in tree.body[0].body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        try:
            field = model._meta.get_field(node.targets[0].id)
        except Exception:
            continue
        if field.many_to_one and 'db_index' not in {kw.arg for kw in node.value.keywords}:
            missing.append(field.name)
    return missing


@checks.register(checks.Tags.models)
def check_explicit_db_index(app_configs, **kwargs):
    from django.apps import apps

    return [
        checks.Warning(
            'ForeignKey without an explicit db_index.',
            hint='Set db_index=True or db_index=False and say why in a comment.',
            obj=model._meta.get_field(name),
            id='conventions.W001',
        )
        for config in (app_configs or apps.get_app_configs())
        if config.name.startswith('labs.')
        for model in config.get_models()
        for name in foreign_keys_without_explicit_db_index(model)
    ]


class IsolatedLabConfig(AppConfig):
    name = 'labs.catalog'
    label = 'catalog'


@isolate_apps('tests.rules.test_detect.IsolatedLabConfig')
@pytest.mark.rule('detect-system-checks')
def test_system_check_flags_implicit_foreign_key_indexes():
    class Shipment(models.Model):
        order = models.ForeignKey('catalog.Category', on_delete=models.CASCADE)
        carrier = models.ForeignKey('catalog.Category', on_delete=models.CASCADE, related_name='+', db_index=False)

        class Meta:
            app_label = 'catalog'

    assert foreign_keys_without_explicit_db_index(Shipment) == ['order']


@pytest.mark.rule('detect-system-checks')
def test_lab_models_pass_the_check():
    assert check_explicit_db_index(None) == []
