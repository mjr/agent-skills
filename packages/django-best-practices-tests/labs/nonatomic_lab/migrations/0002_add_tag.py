"""A non-atomic migration whose second step fails when DBP_FAIL_MIGRATION is set.

See the rule migration-isolate-non-atomic.
"""

import os

from django.db import migrations, models


def second_step(apps, schema_editor):
    if os.environ.get('DBP_FAIL_MIGRATION'):
        raise RuntimeError('simulated failure in the second operation')


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('nonatomic_lab', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='tag',
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.RunPython(second_step, migrations.RunPython.noop),
    ]
