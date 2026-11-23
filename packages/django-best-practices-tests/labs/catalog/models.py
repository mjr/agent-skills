"""Shared models for most rule tests, modelled on the examples in the source articles."""

from django.conf import settings
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=50)


class Product(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(default='')
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='products', db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', db_index=True
    )
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='+',
        null=True,
        db_index=True,
    )
    hits = models.PositiveIntegerField(default=0)


class Tag(models.Model):
    name = models.CharField(max_length=30)
    products = models.ManyToManyField(Product, related_name='tags')


class Order(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_index=True)
    status = models.CharField(max_length=20, default='pending_payment')


class ShortUrl(models.Model):
    key = models.CharField(max_length=20, unique=True)
    target_url = models.URLField()
    hits = models.PositiveIntegerField(default=0)


class Payment(models.Model):
    status = models.CharField(max_length=20, default='initiated')
    paid_at = models.DateTimeField(null=True)


class Wallet(models.Model):
    balance = models.IntegerField(default=0)


class Job(models.Model):
    status = models.CharField(max_length=20, default='pending')
