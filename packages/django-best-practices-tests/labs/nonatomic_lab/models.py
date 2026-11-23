"""A model whose second migration is non-atomic and can be made to fail halfway."""

from django.db import models


class Note(models.Model):
    text = models.CharField(max_length=50)
    tag = models.CharField(max_length=20, null=True)
