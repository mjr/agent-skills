-- Index health report for PostgreSQL 12+.
--
-- Usage:  psql "$DATABASE_URL" -f pg_index_report.sql
--     or  python manage.py dbshell < pg_index_report.sql
--
-- Read-only. Run ANALYZE first for the "mostly-null" check, and remember that
-- "unused" counts scans since the statistics were last reset, on this server only
-- (replicas keep their own counters). Each row is a finding to review, not an
-- instruction: see the index- rules of the django-best-practices skill.

WITH user_indexes AS (
    SELECT
        i.indexrelid,
        i.indrelid,
        i.indisunique,
        i.indisprimary,
        i.indisvalid,
        i.indkey,
        i.indclass,
        i.indcollation,
        i.indpred,
        i.indexprs,
        am.amname
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_am am ON am.oid = c.relam
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
)

-- Never scanned since the last stats reset. Unique and primary keys are excluded:
-- they enforce constraints even when no query reads them.
SELECT
    'unused' AS finding,
    s.relname::text AS table_name,
    s.indexrelname::text AS index_name,
    'idx_scan = 0, size ' || pg_size_pretty(pg_relation_size(s.indexrelid))
        || '; check deletes and rare jobs before dropping' AS detail
FROM pg_stat_user_indexes s
JOIN user_indexes u ON u.indexrelid = s.indexrelid
WHERE s.idx_scan = 0 AND NOT u.indisunique AND NOT u.indisprimary

UNION ALL

-- A plain B-tree whose columns (with the same operator classes and collations) are the
-- leading columns of another B-tree on the same table: the longer index serves the same
-- lookups. Django's "_like" indexes (varchar_pattern_ops) differ in operator class and
-- are not reported.
SELECT
    'redundant',
    a.indrelid::regclass::text,
    a.indexrelid::regclass::text,
    'its columns lead ' || b.indexrelid::regclass::text
FROM user_indexes a
JOIN user_indexes b
    ON b.indrelid = a.indrelid AND b.indexrelid <> a.indexrelid
WHERE NOT a.indisunique
    AND NOT a.indisprimary
    AND a.amname = 'btree' AND b.amname = 'btree'
    AND a.indexprs IS NULL AND b.indexprs IS NULL
    AND a.indpred IS NULL AND b.indpred IS NULL
    AND (
        b.indkey::text LIKE a.indkey::text || ' %'
        OR (b.indkey::text = a.indkey::text AND (b.indisunique OR b.indexrelid < a.indexrelid))
    )
    AND (b.indclass::text LIKE a.indclass::text || ' %' OR b.indclass::text = a.indclass::text)
    AND (b.indcollation::text LIKE a.indcollation::text || ' %' OR b.indcollation::text = a.indcollation::text)

UNION ALL

-- Left behind by a failed or cancelled CREATE INDEX CONCURRENTLY: not used by
-- queries, still updated on every write, and it blocks a retry with the same name.
SELECT
    'invalid',
    u.indrelid::regclass::text,
    u.indexrelid::regclass::text,
    'drop it with DROP INDEX CONCURRENTLY and build it again'
FROM user_indexes u
WHERE NOT u.indisvalid

UNION ALL

-- Single-column, non-partial indexes on mostly-NULL columns: PostgreSQL indexes NULLs,
-- so a partial index (WHERE col IS NOT NULL) is usually far smaller.
SELECT
    'mostly-null',
    t.relname::text,
    c.relname::text,
    round(st.null_frac::numeric * 100) || '% NULL, size '
        || pg_size_pretty(pg_relation_size(u.indexrelid))
FROM user_indexes u
JOIN pg_class c ON c.oid = u.indexrelid
JOIN pg_class t ON t.oid = u.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_attribute att ON att.attrelid = t.oid AND att.attnum = u.indkey[0]
JOIN pg_stats st
    ON st.schemaname = n.nspname AND st.tablename = t.relname AND st.attname = att.attname
WHERE array_length(u.indkey::int2[], 1) = 1
    AND u.indpred IS NULL
    AND u.indexprs IS NULL
    AND NOT u.indisunique
    AND st.null_frac > 0.5

UNION ALL

-- Single-column foreign keys with no index starting with that column: deleting or
-- updating a referenced row scans the whole referencing table.
SELECT
    'fk-without-index',
    con.conrelid::regclass::text,
    con.conname::text,
    'no index starts with ' || att.attname
FROM pg_constraint con
JOIN pg_namespace n ON n.oid = con.connamespace
JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
WHERE con.contype = 'f'
    AND array_length(con.conkey, 1) = 1
    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND NOT EXISTS (
        -- A full index, or a partial one limited to "col IS NOT NULL", serves the lookup;
        -- other partial indexes (WHERE active, ...) do not.
        SELECT 1
        FROM pg_index i
        WHERE i.indrelid = con.conrelid
            AND i.indkey[0] = con.conkey[1]
            AND (
                i.indpred IS NULL
                OR pg_get_expr(i.indpred, i.indrelid) = '(' || quote_ident(att.attname) || ' IS NOT NULL)'
            )
    )

ORDER BY 1, 2, 3;
