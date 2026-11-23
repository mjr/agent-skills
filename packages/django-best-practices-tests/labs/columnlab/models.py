"""Tables that tests alter directly with the schema editor (columns, indexes, constraints)."""

from django.db import models


class Row(models.Model):
    name = models.CharField(max_length=50)
    # Python-side default only: the column is NOT NULL without a database default.
    legacy = models.CharField(max_length=50, default='x')


class RowNextRelease(models.Model):
    """The same table as the next release's code sees it, with legacy already removed."""

    name = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = 'columnlab_row'


class Owner(models.Model):
    name = models.CharField(max_length=50)


class Item(models.Model):
    # A plain integer that a migration later turns into a foreign key to Owner.
    owner_ref = models.IntegerField(null=True)
