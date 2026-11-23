"""admin-date-hierarchy and admin-show-full-result-count.

Older advice indexed EXTRACT(...) expressions for date_hierarchy. Current Django filters
each drill-down level with a plain range on the column, so a regular B-tree index serves
it; the expensive part is the unfiltered DISTINCT DATE_TRUNC that builds the year links.
"""

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from labs.catalog.models import Payment

pytestmark = [pytest.mark.django_db]


def changelist_queries(rf, query_string='', **admin_overrides):
    user, _ = get_user_model().objects.get_or_create(
        username='admin', defaults={'is_staff': True, 'is_superuser': True}
    )
    model_admin = site._registry[Payment]
    original = {name: getattr(model_admin, name) for name in admin_overrides}
    for name, value in admin_overrides.items():
        setattr(model_admin, name, value)
    try:
        request = rf.get(f'/admin/catalog/payment/?{query_string}')
        request.user = user
        with CaptureQueriesContext(connection) as ctx:
            model_admin.changelist_view(request).render()
    finally:
        for name, value in original.items():
            setattr(model_admin, name, value)
    return [q['sql'] for q in ctx.captured_queries if '"catalog_payment"' in q['sql']]


@pytest.mark.rule('admin-date-hierarchy')
@pytest.mark.parametrize(
    'query_string',
    [
        'paid_at__year=2026',
        'paid_at__year=2026&paid_at__month=3',
        'paid_at__year=2026&paid_at__month=3&paid_at__day=5',
    ],
)
def test_drill_down_filters_are_index_friendly_ranges(rf, query_string):
    listing = [q for q in changelist_queries(rf, query_string) if q.startswith('SELECT "catalog_payment"."id"')]
    where = listing[0].split('WHERE', 1)[1]
    assert '"catalog_payment"."paid_at" >= ' in where
    assert '"catalog_payment"."paid_at" < ' in where
    assert 'EXTRACT' not in where


@pytest.mark.rule('admin-date-hierarchy')
def test_top_level_builds_year_links_over_the_whole_table(rf):
    queries = changelist_queries(rf)
    year_links = [q for q in queries if "DATE_TRUNC('year'" in q]
    assert year_links and 'WHERE "catalog_payment"."paid_at" IS NOT NULL' in year_links[0]


@pytest.mark.rule('admin-show-full-result-count')
def test_full_result_count_adds_an_unfiltered_count(rf):
    unfiltered = 'SELECT COUNT(*) AS "__count" FROM "catalog_payment"'

    default = changelist_queries(rf, 'status=paid')
    assert unfiltered in default

    without = changelist_queries(rf, 'status=paid', show_full_result_count=False)
    assert unfiltered not in without
