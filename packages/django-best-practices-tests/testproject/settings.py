"""Minimal settings for the rule tests. Every app under labs/ illustrates one or more rules."""

import importlib.util
import os

SECRET_KEY = 'tests-only'
DEBUG = False
USE_TZ = True
TIME_ZONE = 'UTC'
ROOT_URLCONF = 'testproject.urls'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('PG_HOST', 'localhost'),
        'PORT': os.environ.get('PG_PORT', '55416'),
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'NAME': 'dbp',
    },
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.postgres',
    'labs.catalog',
    'labs.fk_naive',
    'labs.fk_safe',
    'labs.locklab',
]


def _installed(module):
    return importlib.util.find_spec(module) is not None


# Optional database-backed task queues, used by the tx- rules. A queue that does not
# support the running Django version is left out and its tests are skipped.
# Django 6.0+ ships the tasks framework as django.tasks; on 5.2 the django-tasks backport
# provides it. Either way the database backend comes from django-tasks-db.
HAS_TASKS_DB = _installed('django_tasks_db')
HAS_DJANGO_Q = _installed('django_q')

if HAS_TASKS_DB:
    if _installed('django_tasks'):
        INSTALLED_APPS += ['django_tasks']
    INSTALLED_APPS += ['django_tasks_db']
    TASKS = {'default': {'BACKEND': 'django_tasks_db.DatabaseBackend', 'QUEUES': ['default']}}

if HAS_DJANGO_Q:
    INSTALLED_APPS += ['django_q']
    Q_CLUSTER = {'name': 'tests', 'orm': 'default', 'sync': False, 'timeout': 60, 'retry': 120}

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
