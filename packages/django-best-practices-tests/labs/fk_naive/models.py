"""Parent/child pair whose foreign key index is dropped by migration 0002."""

from django.db import models


class Parent(models.Model):
    name = models.CharField(max_length=50)


class Child(models.Model):
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT, db_index=False)
