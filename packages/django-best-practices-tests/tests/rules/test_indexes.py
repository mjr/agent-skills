"""index- rules, checked with EXPLAIN, catalog sizes and the pg_index_report.sql script."""

import pathlib
from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.postgres.indexes import BrinIndex
from django.db import IntegrityError, connection, models, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from labs.catalog.models import Category, Product
from labs.indexlab.models import Account, Membership, Ticket, Voucher
from tests.helpers import index_names, sqlmigrate, migrate

pytestmark = [pytest.mark.django_db(transaction=True)]

User = get_user_model()
REPORT = (
    pathlib.Path(__file__).resolve().parents[4]
    / 'skills/django-best-practices/scripts/pg_index_report.sql'
)


@contextmanager
def index_scans_preferred():
    """Disable sequential scans so EXPLAIN shows which index can serve a query."""
    with connection.cursor() as cursor:
        cursor.execute('SET enable_seqscan = off')
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SET enable_seqscan = on')


def analyze(table):
    with connection.cursor() as cursor:
        cursor.execute(f'ANALYZE {table}')


def index_size(name):
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_relation_size(%s::regclass)', [name])
        return cursor.fetchone()[0]


@pytest.fixture
def tickets():
    users = [User.objects.create_user(f'agent{i}') for i in range(3)]
    accounts = [Account.objects.create(name=f'account {i}') for i in range(20)]
    now = timezone.now()
    Ticket.objects.bulk_create(
        Ticket(
            account=accounts[i % 20],
            number=i,
            assignee=users[i % 3] if i % 100 == 0 else None,  # 1% assigned.
            opened_at=now + timedelta(seconds=i),
        )
        for i in range(20_000)
    )
    analyze('indexlab_ticket')
    return accounts, users


# index-explicit-fk-db-index


@pytest.mark.rule('index-explicit-fk-db-index')
def test_foreign_keys_get_an_index_unless_told_otherwise():
    migrate('fk_naive', '0001')
    try:
        assert 'CREATE INDEX' in sqlmigrate('fk_naive', '0001')
        assert 'fk_naive_child_parent_id_4b951ec7' in index_names('fk_naive_child')
    finally:
        migrate('fk_naive', '0002')


@pytest.mark.rule('index-explicit-fk-db-index')
def test_db_index_false_creates_none():
    assert {n for n in index_names('indexlab_ticket') if 'account_id' in n} == set()


# index-fk-index-for-deletes


@pytest.mark.rule('index-fk-index-for-deletes')
def test_deleting_a_row_queries_every_table_that_references_it():
    user = User.objects.create_user('leaving')
    with CaptureQueriesContext(connection) as ctx:
        user.delete()
    lookups = [q['sql'] for q in ctx.captured_queries if '"created_by_id" IN' in q['sql']]
    assert lookups, 'Django looks for products created by the user before deleting it'


@pytest.mark.rule('index-fk-index-for-deletes')
def test_that_lookup_can_only_use_an_index_if_one_exists():
    user = User.objects.create_user('leaving')
    with index_scans_preferred():
        with_index = Product.objects.filter(created_by_id__in=[user.pk]).explain()
        unindexed = Membership.objects.filter(user_id__in=[user.pk]).explain()  # db_index=False
    assert 'Index' in with_index
    assert 'Seq Scan' in unindexed


# index-composite-leading-column


@pytest.mark.rule('index-composite-leading-column')
def test_leading_column_of_a_composite_index_serves_its_own_lookups(tickets):
    accounts, _ = tickets
    with index_scans_preferred():
        plan = Ticket.objects.filter(account=accounts[0]).explain()
    assert 'ticket_account_number_uk' in plan
    assert 'Index Cond: (account_id =' in plan


@pytest.mark.rule('index-composite-leading-column')
def test_second_column_alone_needs_its_own_index(tickets):
    """Left to the planner: PostgreSQL 16 scans the table; 18 can skip-scan the index.

    The skip scan only pays off because the leading column has few distinct values (20
    accounts here); with many, PostgreSQL 18 also falls back to a full scan.
    """
    plan = Ticket.objects.filter(number=42).explain()
    if connection.pg_version < 180000:
        assert plan.startswith('Seq Scan')
    else:
        assert 'Index Scan using ticket_account_number_uk' in plan


@pytest.mark.rule('index-composite-leading-column')
def test_both_columns_use_the_composite_index(tickets):
    accounts, _ = tickets
    plan = Ticket.objects.filter(account=accounts[3], number=43).explain()
    assert 'Index Scan using ticket_account_number_uk' in plan


# index-partial-sparse


@pytest.mark.rule('index-partial-sparse')
def test_nulls_are_indexed_so_a_full_index_on_a_sparse_column_is_large(tickets):
    full = models.Index(fields=['assignee'], name='ticket_assignee_full_ix')
    with connection.schema_editor() as editor:
        editor.add_index(Ticket, full)
    try:
        # 20k rows, 1% set: the partial index is at its two-page minimum.
        assert index_size('ticket_assignee_full_ix') > 5 * index_size('ticket_assignee_part_ix')
    finally:
        with connection.schema_editor() as editor:
            editor.remove_index(Ticket, full)


@pytest.mark.rule('index-partial-sparse')
def test_equality_lookups_can_use_the_partial_index(tickets):
    _, users = tickets
    with index_scans_preferred():
        plan = Ticket.objects.filter(assignee=users[0]).explain()
    assert 'ticket_assignee_part_ix' in plan


# index-unique-constraint


@pytest.mark.rule('index-unique-constraint')
def test_partial_unique_constraint_allows_history_but_one_active_row():
    user = User.objects.create_user('member')
    Membership.objects.create(user=user, team='ops', active=False)
    Membership.objects.create(user=user, team='ops', active=False)
    Membership.objects.create(user=user, team='ops', active=True)
    with pytest.raises(IntegrityError, match='membership_one_active_per_team_uk'):
        with transaction.atomic():
            Membership.objects.create(user=user, team='ops', active=True)


@pytest.mark.rule('index-unique-constraint')
def test_nulls_are_distinct_unless_the_constraint_says_otherwise():
    Voucher.objects.create(code=None)
    with pytest.raises(IntegrityError, match='voucher_code_uk'):
        with transaction.atomic():
            Voucher.objects.create(code=None)


# index-brin-correlated


@pytest.mark.rule('index-brin-correlated')
def test_brin_is_tiny_on_a_column_that_follows_insert_order(tickets):
    btree = models.Index(fields=['opened_at'], name='ticket_opened_btree_ix')
    brin = BrinIndex(fields=['opened_at'], name='ticket_opened_brin_ix')
    with connection.schema_editor() as editor:
        editor.add_index(Ticket, btree)
        editor.add_index(Ticket, brin)
    try:
        assert index_size('ticket_opened_btree_ix') > 10 * index_size('ticket_opened_brin_ix')
        with index_scans_preferred(), connection.cursor() as cursor:
            cursor.execute('DROP INDEX ticket_opened_btree_ix')
            plan = Ticket.objects.filter(opened_at__gte=timezone.now()).explain()
        assert 'Bitmap Index Scan on ticket_opened_brin_ix' in plan
    finally:
        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX IF EXISTS ticket_opened_btree_ix')
            cursor.execute('DROP INDEX IF EXISTS ticket_opened_brin_ix')


# index-audit-unused-and-duplicate


def report():
    with connection.cursor() as cursor:
        cursor.execute(REPORT.read_text())
        return cursor.fetchall()


@pytest.mark.rule('index-audit-unused-and-duplicate')
def test_report_finds_redundant_mostly_null_and_unindexed_foreign_keys(tickets):
    redundant = models.Index(fields=['account'], name='ticket_account_only_ix')
    full = models.Index(fields=['assignee'], name='ticket_assignee_full_ix')
    with connection.schema_editor() as editor:
        editor.add_index(Ticket, redundant)
        editor.add_index(Ticket, full)
    analyze('indexlab_ticket')
    try:
        findings = {(f, t, i) for f, t, i, _ in report()}
    finally:
        with connection.schema_editor() as editor:
            editor.remove_index(Ticket, redundant)
            editor.remove_index(Ticket, full)

    assert ('redundant', 'indexlab_ticket', 'ticket_account_only_ix') in findings
    assert ('mostly-null', 'indexlab_ticket', 'ticket_assignee_full_ix') in findings
    assert ('unused', 'indexlab_ticket', 'ticket_account_only_ix') in findings
    unindexed_fks = {t for f, t, _ in findings if f == 'fk-without-index'}
    assert 'indexlab_membership' in unindexed_fks  # db_index=False and no covering index.
    assert 'indexlab_ticket' not in unindexed_fks  # Covered by the unique and partial indexes.


@pytest.mark.rule('index-audit-unused-and-duplicate')
def test_report_finds_invalid_indexes():
    with connection.cursor() as cursor:
        cursor.execute('CREATE INDEX ticket_broken_ix ON indexlab_ticket (number)')
        cursor.execute(
            "UPDATE pg_index SET indisvalid = false WHERE indexrelid = 'ticket_broken_ix'::regclass"
        )
    try:
        assert ('invalid', 'indexlab_ticket', 'ticket_broken_ix') in {(f, t, i) for f, t, i, _ in report()}
    finally:
        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX ticket_broken_ix')


@pytest.mark.rule('index-audit-unused-and-duplicate')
def test_report_does_not_call_like_indexes_redundant():
    """Django adds a varchar_pattern_ops "_like" index next to unique and indexed CharFields."""
    like = {i for i in index_names('catalog_shorturl') if i.endswith('_like')}
    assert like, 'the lab model should have a _like index'
    redundant = {i for f, t, i, _ in report() if f == 'redundant' and t == 'catalog_shorturl'}
    assert not like & redundant


@pytest.mark.rule('index-composite-leading-column')
def test_auto_created_many_to_many_tables_carry_a_redundant_index():
    """Django indexes both foreign keys of an implicit through table and adds a unique
    (a, b) constraint, whose leading column makes the index on a redundant."""
    findings = {(f, t) for f, t, _, _ in report()}
    assert ('redundant', 'catalog_tag_products') in findings
