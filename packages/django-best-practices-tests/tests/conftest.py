import pytest
from django.contrib.auth import get_user_model

from labs.catalog.models import Category, Product


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user('author')


@pytest.fixture
def product(user):
    category = Category.objects.create(name='fruit')
    return Product.objects.create(name='apple', category=category, created_by=user)
