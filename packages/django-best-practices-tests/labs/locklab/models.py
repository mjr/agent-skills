"""A table that another session keeps busy while a migration tries to alter it."""

from django.db import models


class Ledger(models.Model):
    name = models.CharField(max_length=50)
