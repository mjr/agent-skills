#!/usr/bin/env python3
"""Validate the django-best-practices rules and keep SKILL.md's quick reference in sync.

    python validate_rules.py           check everything, exit 1 on problems
    python validate_rules.py --write   also regenerate the quick reference in SKILL.md

Checks, for every rules/<prefix>-<name>.md:
- frontmatter fields and allowed values; the title matches the first heading;
- the prefix belongs to a section in rules/_sections.md;
- required parts: Correct example, "When not to apply", "How to detect", Reference;
- the tests file exists and marks the rule with @pytest.mark.rule('<id>'), or the rule
  says "tests: none: <reason>";
- rule ids mentioned in backticks exist;
and that every @pytest.mark.rule id in the tests names an existing rule.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parents[1] / 'skills' / 'django-best-practices'
RULES = SKILL / 'rules'
TESTS = HERE / 'tests' / 'rules'

IMPACTS = ['CRITICAL', 'HIGH', 'MEDIUM-HIGH', 'MEDIUM', 'LOW-MEDIUM', 'LOW']
RISKS = {'correctness', 'availability', 'performance', 'cost'}
DATABASES = {'any', 'postgresql'}
REQUIRED = ['**Correct', '**When not to apply:**', '**How to detect:**', 'Reference:']
START, END = '<!-- quick-reference:start -->', '<!-- quick-reference:end -->'


def frontmatter(text):
    match = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not match:
        return None, text
    data, key = {}, None
    for line in match.group(1).splitlines():
        if line.startswith('  - ') and key:
            data.setdefault(key, []).append(line[4:].strip())
        elif ':' in line and not line.startswith(' '):
            key, value = line.split(':', 1)
            value = value.split('  #')[0].strip().strip('"')
            data[key.strip()] = value if value else []
    return data, text[match.end():]


def sections():
    found = {}
    for m in re.finditer(r'^## (\d+)\. (.+?) \((\w+)-\)\n\n\*\*Impact:\*\* (\S+)', (RULES / '_sections.md').read_text(), re.M):
        found[m.group(3)] = {'order': int(m.group(1)), 'title': m.group(2), 'impact': m.group(4)}
    return found


def load_rules():
    rules = {}
    for path in sorted(RULES.glob('*.md')):
        if path.name.startswith('_'):
            continue
        meta, body = frontmatter(path.read_text())
        rules[path.stem] = {'path': path, 'meta': meta, 'body': body}
    return rules


def marked_rule_ids():
    ids = {}
    for path in TESTS.glob('test_*.py'):
        for rule_id in re.findall(r"mark\.rule\('([\w-]+)'\)", path.read_text()):
            ids.setdefault(rule_id, set()).add(path.name)
    return ids


def validate(rules, known_sections, marks):
    errors = []
    for rule_id, rule in rules.items():
        meta, body, name = rule['meta'], rule['body'], rule['path'].name
        if meta is None:
            errors.append(f'{name}: missing frontmatter')
            continue
        for field in ('title', 'impact', 'risk', 'django', 'database', 'tags', 'sources', 'tests'):
            if not meta.get(field):
                errors.append(f'{name}: missing {field}')
        if meta.get('impact') not in IMPACTS:
            errors.append(f'{name}: impact {meta.get("impact")!r} not in {IMPACTS}')
        if meta.get('risk') not in RISKS:
            errors.append(f'{name}: risk {meta.get("risk")!r} not in {sorted(RISKS)}')
        if meta.get('database') not in DATABASES:
            errors.append(f'{name}: database {meta.get("database")!r} not in {sorted(DATABASES)}')
        if not re.fullmatch(r'>=\d+\.\d+', meta.get('django', '')):
            errors.append(f'{name}: django must look like ">=5.2"')
        if not isinstance(meta.get('sources'), list):
            errors.append(f'{name}: sources must be a list of URLs')
        prefix = rule_id.split('-', 1)[0]
        if prefix not in known_sections:
            errors.append(f'{name}: prefix {prefix!r} has no section in _sections.md')
        heading = re.search(r'^## (.+)$', body, re.M)
        if not heading or heading.group(1).strip() != meta.get('title'):
            errors.append(f'{name}: first heading must repeat the title')
        for part in REQUIRED:
            if part not in body:
                errors.append(f'{name}: missing {part!r}')

        tests = meta.get('tests', '')
        if tests.startswith('none:'):
            if len(tests) < 12:
                errors.append(f'{name}: "tests: none:" needs a reason')
        else:
            for test_file in [t.strip() for t in tests.split(',') if t.strip()]:
                if not (TESTS / test_file).exists():
                    errors.append(f'{name}: tests file {test_file} does not exist')
            if rule_id not in marks:
                errors.append(f"{name}: no test is marked @pytest.mark.rule('{rule_id}')")

        for mentioned in set(re.findall(r'`((?:' + '|'.join(known_sections) + r')-[a-z0-9-]+)`', body)):
            if mentioned not in rules:
                errors.append(f'{name}: mentions unknown rule {mentioned}')

    for rule_id, files in marks.items():
        if rule_id not in rules:
            errors.append(f'tests {sorted(files)}: mark unknown rule {rule_id!r}')
    return errors


def quick_reference(rules, known_sections):
    lines = []
    for prefix, section in sorted(known_sections.items(), key=lambda s: s[1]['order']):
        members = [(rid, r) for rid, r in rules.items() if rid.startswith(prefix + '-')]
        members.sort(key=lambda item: (IMPACTS.index(item[1]['meta']['impact']), item[0]))
        lines.append(f"### {section['order']}. {section['title']} (`{prefix}-`)\n")
        for rule_id, rule in members:
            meta = rule['meta']
            extras = []
            if meta['django'] != '>=5.2':
                extras.append(f"Django {meta['django']}")
            if meta['database'] == 'postgresql':
                extras.append('PostgreSQL')
            suffix = f" ({', '.join(extras)})" if extras else ''
            lines.append(f"- `{rule_id}` [{meta['impact']}] {meta['title']}{suffix}")
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main(argv):
    known_sections = sections()
    rules = load_rules()
    errors = validate(rules, known_sections, marked_rule_ids())

    skill_md = SKILL / 'SKILL.md'
    text = skill_md.read_text()
    generated = f'{START}\n{quick_reference(rules, known_sections)}{END}'
    current = re.search(re.escape(START) + '.*?' + re.escape(END), text, re.S)
    if not current:
        errors.append('SKILL.md: quick reference markers not found')
    elif current.group(0) != generated:
        if '--write' in argv:
            skill_md.write_text(text.replace(current.group(0), generated))
            print('SKILL.md quick reference updated', file=sys.stderr)
        else:
            errors.append('SKILL.md: quick reference is out of date (run with --write)')

    if len(skill_md.read_text().splitlines()) > 500:
        errors.append('SKILL.md: keep it under 500 lines')

    for error in errors:
        print(f'error: {error}', file=sys.stderr)
    print(f'{len(rules)} rules, {len(errors)} problems', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
