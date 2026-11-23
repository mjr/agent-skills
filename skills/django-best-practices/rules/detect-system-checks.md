---
title: Turn conventions into system checks
impact: MEDIUM
risk: correctness
django: ">=4.2"
database: any
tags: system-checks, conventions, ast, db_index, ci
sources:
  - https://hakibenita.com/automating-the-boring-stuff-in-django-using-the-check-framework
  - https://hakibenita.com/django-rest-framework-slow
tests: test_detect.py
---

## Turn conventions into system checks

Conventions that live only in a guide ("set `db_index` explicitly", "every model has a
`verbose_name`") erode with each new contributor. Django's system check framework runs on
`manage.py check`, `runserver`, `migrate` and the test runner, so a check turns a
convention into a warning at the moment code is written.

Some conventions cannot be read from the model at runtime because Django fills in the
defaults (a `ForeignKey` ends up with `db_index=True` either way). Those checks read the
source of the model class.

**Correct (warn on foreign keys without an explicit db_index):**

```python
# yourapp/checks.py, imported from AppConfig.ready()
import ast
import inspect
import textwrap

from django.apps import apps
from django.core import checks


def foreign_keys_without_explicit_db_index(model):
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(model)))
    except (OSError, TypeError):  # Models built at runtime have no source.
        return []
    missing = []
    for node in tree.body[0].body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        try:
            field = model._meta.get_field(node.targets[0].id)
        except Exception:
            continue
        if field.many_to_one and 'db_index' not in {kw.arg for kw in node.value.keywords}:
            missing.append(field.name)
    return missing


@checks.register(checks.Tags.models)
def check_explicit_db_index(app_configs, **kwargs):
    return [
        checks.Warning(
            'ForeignKey without an explicit db_index.',
            hint='Set db_index=True or db_index=False and say why in a comment.',
            obj=model._meta.get_field(name),
            id='conventions.W001',
        )
        for config in (app_configs or apps.get_app_configs())
        if config.name.startswith('yourproject.')
        for model in config.get_models()
        for name in foreign_keys_without_explicit_db_index(model)
    ]
```

Return `Warning`, not `Error`: `migrate` runs checks too, and an `Error` would block a
deploy over a convention. Enforce in CI with `manage.py check --fail-level WARNING`, or a
test that asserts the check returns nothing. Other conventions that fit this pattern:
`read_only_fields` on DRF serializers (see `drf-read-only-fields`), named
`UniqueConstraint`s, `dispatch_uid` on receivers.

**When not to apply:** checks that parse source are heuristics; keep them simple, limit
them to first-party apps and skip what they cannot read instead of failing.

**How to detect:** conventions written in the contributing guide or review comments
that keep being repeated.

Reference: [Automating the Boring Stuff in Django Using the Check Framework](https://hakibenita.com/automating-the-boring-stuff-in-django-using-the-check-framework)
