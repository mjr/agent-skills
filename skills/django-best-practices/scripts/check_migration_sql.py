#!/usr/bin/env python3
"""Flag risky statements in the SQL of a Django migration (PostgreSQL).

Usage:
    python manage.py sqlmigrate <app> <migration> | python check_migration_sql.py
    python check_migration_sql.py migration.sql

Run sqlmigrate against a database migrated up to the previous migration: Django reads
constraint names from the live database and prints "(no-op)" when it cannot find them.

Writes a JSON list of findings to stdout and a readable summary to stderr. Exits with 1
when a finding has severity "high", 0 otherwise. Uses only the standard library.
"""

import json
import re
import sys

NAME = r'"?([\w$]+)"?'


def statements(sql):
    """Split SQL into (operation_header, statement) pairs, keeping sqlmigrate's headers."""
    header, pending, result = None, [], []
    for raw in sql.splitlines():
        line = raw.strip()
        if line.startswith('--'):
            text = line.lstrip('-').strip()
            if text == '(no-op)':
                result.append((header, '(no-op)'))
            elif text:
                header = text
            continue
        if not line or line in ('BEGIN;', 'COMMIT;'):
            continue
        pending.append(line)
        if line.endswith(';'):
            result.append((header, ' '.join(pending)))
            pending = []
    if pending:
        result.append((header, ' '.join(pending)))
    return result


def created_tables(parsed):
    return {
        m.group(1)
        for _, stmt in parsed
        for m in [re.match(r'CREATE TABLE ' + NAME, stmt, re.I)]
        if m
    }


def table_of(stmt):
    m = re.search(r'(?:ALTER TABLE|ON)\s+(?:ONLY\s+)?' + NAME, stmt, re.I)
    return m.group(1) if m else None


def check(sql):
    parsed = statements(sql)
    new_tables = created_tables(parsed)
    findings = []

    def add(severity, rule, message, header, stmt):
        findings.append(
            {
                'severity': severity,
                'rule': rule,
                'message': message,
                'operation': header,
                'statement': stmt[:300],
            }
        )

    dropped_constraints = set()
    for header, stmt in parsed:
        upper = stmt.upper()
        table = table_of(stmt)
        existing_table = table not in new_tables

        if stmt == '(no-op)':
            if header and re.match(r'(Alter|Remove|Rename) ', header):
                add(
                    'medium',
                    'migration-review-sql',
                    'sqlmigrate printed no SQL for this operation. If the database it ran '
                    'against is not at the previous migration, the real SQL can differ '
                    '(for example, a foreign key that is dropped and re-created).',
                    header,
                    stmt,
                )
            continue

        m = re.search(r'DROP CONSTRAINT\s+' + NAME, stmt, re.I)
        if m:
            dropped_constraints.add(m.group(1))

        m = re.search(r'ADD CONSTRAINT\s+' + NAME + r'\s+FOREIGN KEY', stmt, re.I)
        if m and existing_table:
            if m.group(1) in dropped_constraints:
                add(
                    'high',
                    'migration-fk-db-index-change',
                    'The foreign key is dropped and re-created: the table is locked while '
                    'every row is checked again. Use SeparateDatabaseAndState to change '
                    'only the index.',
                    header,
                    stmt,
                )
            elif 'NOT VALID' not in upper:
                add(
                    'medium',
                    'migration-fk-not-valid',
                    'Adding a foreign key validates every existing row and blocks writes '
                    'to both tables meanwhile. On a populated column, add it NOT VALID and '
                    'VALIDATE CONSTRAINT separately.',
                    header,
                    stmt,
                )

        if re.match(r'CREATE (UNIQUE )?INDEX', upper) and 'CONCURRENTLY' not in upper and existing_table:
            add(
                'medium',
                'migration-concurrent-indexes',
                'CREATE INDEX blocks writes to the table until the migration commits. On a '
                'large or busy table use AddIndexConcurrently in a non-atomic migration.',
                header,
                stmt,
            )

        if re.match(r'DROP INDEX', upper) and 'CONCURRENTLY' not in upper:
            add(
                'medium',
                'migration-concurrent-indexes',
                'DROP INDEX takes an ACCESS EXCLUSIVE lock on the table. Use '
                'RemoveIndexConcurrently (or DROP INDEX CONCURRENTLY).',
                header,
                stmt,
            )

        if 'SET NOT NULL' in upper and existing_table:
            add(
                'medium',
                'migration-set-not-null-in-steps',
                'SET NOT NULL scans the whole table under an ACCESS EXCLUSIVE lock. On a '
                'large table, validate a CHECK (col IS NOT NULL) constraint first.',
                header,
                stmt,
            )

        if re.search(r'ALTER COLUMN\s+' + NAME + r'\s+TYPE', stmt, re.I) and existing_table:
            add(
                'medium',
                'migration-review-sql',
                'Changing a column type can rewrite the table under an ACCESS EXCLUSIVE '
                'lock (increasing a varchar length does not).',
                header,
                stmt,
            )

        if re.search(r'ADD COLUMN .*DEFAULT\s+\(?\s*(GEN_RANDOM_UUID|RANDOM|CLOCK_TIMESTAMP|UUID_GENERATE)', upper):
            add(
                'high',
                'migration-add-column-defaults',
                'A volatile default rewrites every row of the table while holding an '
                'ACCESS EXCLUSIVE lock.',
                header,
                stmt,
            )

        if re.search(r'DROP COLUMN|RENAME COLUMN|RENAME TO|^DROP TABLE', upper) and existing_table:
            add(
                'medium',
                'migration-deploy-compatible',
                'Code that is still running during the deploy may use this column or '
                'table. Stop using it in an earlier release.',
                header,
                stmt,
            )

    alters = [stmt for _, stmt in parsed if stmt.upper().startswith('ALTER TABLE')]
    if alters and 'LOCK_TIMEOUT' not in sql.upper():
        add(
            'info',
            'migration-lock-timeout',
            'No lock_timeout is set. A statement waiting for a lock blocks every later '
            'query on the table; set lock_timeout for the migrate process.',
            None,
            alters[0],
        )

    if parsed and 'BEGIN;' not in sql:
        others = [
            stmt
            for _, stmt in parsed
            if stmt != '(no-op)' and 'CONCURRENTLY' not in stmt.upper()
        ]
        if others:
            add(
                'medium',
                'migration-isolate-non-atomic',
                'This migration is not atomic and also contains operations other than '
                'concurrent index changes. A failure halfway leaves them applied and the '
                'migration unrecorded; move them to an atomic migration.',
                None,
                others[0],
            )

    return findings


def main(argv):
    sql = open(argv[1]).read() if len(argv) > 1 else sys.stdin.read()
    findings = check(sql)
    json.dump(findings, sys.stdout, indent=2)
    sys.stdout.write('\n')
    for f in findings:
        print(f"[{f['severity']}] {f['rule']}: {f['message']}", file=sys.stderr)
        print(f"    {f['statement'][:160]}", file=sys.stderr)
    if not findings:
        print('No risky statements found.', file=sys.stderr)
    return 1 if any(f['severity'] == 'high' for f in findings) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
