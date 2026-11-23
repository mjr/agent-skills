"""The safe version of fk_naive 0002: same state change, but only the index is dropped.

See the rule migration-fk-db-index-change.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    # DROP/CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    atomic = False

    dependencies = [
        ('fk_safe', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='child',
                    name='parent',
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        to='fk_safe.parent',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY IF EXISTS "fk_safe_child_parent_id_7e074e51"',
                    # Taken from `sqlmigrate fk_safe 0001`.
                    reverse_sql=(
                        'CREATE INDEX CONCURRENTLY "fk_safe_child_parent_id_7e074e51" '
                        'ON "fk_safe_child" ("parent_id")'
                    ),
                ),
            ],
        ),
    ]
