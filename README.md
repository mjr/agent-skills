# Agent skills

Skills for AI coding agents.

| Skill | What it covers |
| --- | --- |
| [django-best-practices](skills/django-best-practices/SKILL.md) | Django on PostgreSQL: concurrency, transactions, migrations, signals, queries, indexes, DRF, admin and database operations, verified by executable tests |

## Install

With [skills.sh](https://skills.sh):

```bash
npx skills add <path-or-url-of-this-repo> --skill django-best-practices -g
```

or copy the folder for Claude Code:

```bash
cp -r skills/django-best-practices ~/.claude/skills/
```

## Layout

```
skills/django-best-practices/       the skill that gets installed
  SKILL.md                          index: when to use, categories, checklist, quick reference
  metadata.json                     version, verified versions, references
  rules/                            one rule per file; _sections.md and _template.md
  scripts/                          check_migration_sql.py, pg_index_report.sql
packages/django-best-practices-tests/
                                    executable tests for the rules (not installed)
archive/                            earlier skill versions, kept compressed for history
```

## Working on django-best-practices

Every rule states claims that a test in `packages/django-best-practices-tests` checks
against a real PostgreSQL, on every supported Django version:

```bash
cd packages/django-best-practices-tests
docker compose up -d pg16 pg18
./run_matrix.sh                    # Django 5.2, 6.0, 6.1 on PostgreSQL 16
PG_PORT=55418 ./run_matrix.sh      # the same on PostgreSQL 18
python3 validate_rules.py --write  # validate rules and regenerate the quick reference
```

To add a rule: copy `rules/_template.md` to `rules/<prefix>-<name>.md`, write a test in
`tests/rules/` marked `@pytest.mark.rule('<prefix>-<name>')`, run the matrix, then
`validate_rules.py --write`. A rule only states what its test confirms on every version;
where versions differ, the rule says so and the test checks each behavior.
