"""migration-reversible."""

import pytest
from django.db import connection, migrations
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.state import ProjectState

pytestmark = [pytest.mark.django_db, pytest.mark.rule('migration-reversible')]


def forwards(apps, schema_editor):
    pass


def test_operations_without_a_reverse_are_irreversible():
    assert not migrations.RunSQL('SELECT 1').reversible
    assert not migrations.RunPython(forwards).reversible
    assert migrations.RunSQL('SELECT 1', reverse_sql='SELECT 1').reversible
    assert migrations.RunPython(forwards, migrations.RunPython.noop).reversible


def test_unapplying_an_irreversible_migration_fails():
    migration = migrations.Migration('0002_backfill', 'catalog')
    migration.operations = [migrations.RunPython(forwards)]
    with pytest.raises(IrreversibleError):
        with connection.schema_editor() as editor:
            migration.unapply(ProjectState(), editor)
