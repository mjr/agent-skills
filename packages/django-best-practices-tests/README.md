# django-best-practices tests

Executable checks for the claims made by the rules in
`skills/django-best-practices/rules/`. Each test is marked with the rule it verifies:
`@pytest.mark.rule('migration-fk-db-index-change')`.

## Run

Requires Docker and [uv](https://docs.astral.sh/uv/). Nothing is installed globally:
every Django version runs in its own throwaway environment.

```bash
docker compose up -d pg16 pg18
./run_matrix.sh                         # Django 5.2, 6.0 and 6.1 on PostgreSQL 16
PG_PORT=55418 ./run_matrix.sh           # on PostgreSQL 18
DJANGO_VERSIONS=6.1 ./run_matrix.sh -k concurrency   # one version, some tests
./dj.sh 6.1 python manage.py sqlmigrate fk_naive 0002 # any command on one version
python3 validate_rules.py               # rule files, test links, quick reference
```

## Layout

- `testproject/`: settings and URLs. Optional queues (django-tasks-db, django-q2) are
  enabled when installed; their tests are skipped otherwise.
- `labs/`: small apps whose models and migrations reproduce each situation:
  `catalog` (shared models), `fk_naive`/`fk_safe` (foreign key index migrations),
  `locklab`, `columnlab`, `nonatomic_lab`, `indexlab`.
- `tests/helpers.py`: migration control, catalog inspection, and `Session`, a second
  database connection on its own thread for lock and visibility tests.
- `tests/rules/`: one or more test files per rule category.

## Writing tests for a rule

- Show the failure, then the fix. A test that only shows the fix proves nothing about
  the rule.
- Use real concurrency for locking claims: hold a lock with `Session.atomic_hold()` and
  probe from another connection with `lock_timeout`, instead of reasoning about it.
- When Django or PostgreSQL versions behave differently, test each behavior with
  `skipif` on the version and say so in the rule.
- Prove the test can fail: break the condition once (a mutation check) before trusting
  a green run.
