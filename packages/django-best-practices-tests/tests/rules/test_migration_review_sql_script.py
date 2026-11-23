"""migration-review-sql: the check_migration_sql.py script against real sqlmigrate output."""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

from tests.helpers import migrate, sqlmigrate

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.rule('migration-review-sql')]

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[4]
    / 'skills/django-best-practices/scripts/check_migration_sql.py'
)
spec = importlib.util.spec_from_file_location('check_migration_sql', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def rules(sql):
    return {(f['severity'], f['rule']) for f in checker.check(sql)}


@pytest.fixture
def labs_at_0001():
    migrate('fk_naive', '0001')
    migrate('fk_safe', '0001')
    yield
    migrate('fk_naive', '0002')
    migrate('fk_safe', '0002')


def test_flags_a_recreated_foreign_key_when_turning_the_index_on():
    # At 0002 (no index), going back to 0001 sets db_index=True again.
    assert ('high', 'migration-fk-db-index-change') in rules(sqlmigrate('fk_naive', '0002', backwards=True))


def test_flags_a_recreated_foreign_key(labs_at_0001):
    assert ('high', 'migration-fk-db-index-change') in rules(sqlmigrate('fk_naive', '0002'))


def test_accepts_the_separate_database_and_state_version(labs_at_0001):
    found = rules(sqlmigrate('fk_safe', '0002'))
    assert not {r for r in found if r[0] in ('high', 'medium')}


def test_flags_a_hidden_no_op_on_an_unmigrated_database():
    migrate('fk_naive', 'zero')
    try:
        sql = sqlmigrate('fk_naive', '0002')
    finally:
        migrate('fk_naive', '0002')
    assert ('info', 'migration-review-sql') in rules(sql)


def test_flags_non_atomic_migrations_that_mix_operations():
    assert ('medium', 'migration-isolate-non-atomic') in rules(sqlmigrate('nonatomic_lab', '0002'))


def test_accepts_a_migration_that_only_creates_tables():
    found = rules(sqlmigrate('catalog', '0001'))
    assert not {r for r in found if r[0] in ('high', 'medium')}


@pytest.mark.parametrize(
    'statement, expected',
    [
        ('CREATE INDEX "ix" ON "t" ("c");', 'migration-concurrent-indexes'),
        ('DROP INDEX IF EXISTS "ix";', 'migration-concurrent-indexes'),
        ('ALTER TABLE "t" ALTER COLUMN "c" SET NOT NULL;', 'migration-set-not-null-in-steps'),
        ('ALTER TABLE "t" ADD COLUMN "u" uuid DEFAULT (GEN_RANDOM_UUID()) NOT NULL;', 'migration-add-column-defaults'),
        ('ALTER TABLE "t" DROP COLUMN "c" CASCADE;', 'migration-deploy-compatible'),
        ('ALTER TABLE "t" ADD CONSTRAINT "fk" FOREIGN KEY ("c") REFERENCES "p" ("id");', 'migration-fk-not-valid'),
    ],
)
def test_flags_each_risky_statement(statement, expected):
    sql = f'BEGIN;\n--\n-- Some operation\n--\n{statement}\nCOMMIT;\n'
    assert expected in {rule for _, rule in rules(sql)}


def test_command_line_exit_code_and_json(labs_at_0001):
    sql = sqlmigrate('fk_naive', '0002')
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], input=sql, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert '"migration-fk-db-index-change"' in result.stdout
    assert 'migration-fk-db-index-change' in result.stderr
