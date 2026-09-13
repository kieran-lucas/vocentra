"""Back up before upgrading and compare every application table afterward."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=['before', 'after'])
parser.add_argument('database', type=Path)
parser.add_argument('backup', type=Path)
args = parser.parse_args()
db = sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)


def snapshot(connection):
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='_sqlx_migrations' ORDER BY name")]
    result = {}
    for table in tables:
        identifier = '"' + table.replace('"', '""') + '"'
        rows = sorted(json.dumps(row, ensure_ascii=False, default=repr) for row in connection.execute(f'SELECT * FROM {identifier}'))
        digest = hashlib.sha256('\n'.join(rows).encode()).hexdigest()
        result[table] = {'rows': len(rows), 'sha256': digest}
    return result


if args.action == 'before':
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    if args.backup.exists():
        raise SystemExit('Refusing to overwrite an existing upgrade backup')
    with sqlite3.connect(args.backup) as backup:
        db.backup(backup)
    print(json.dumps({'backup': str(args.backup), 'tables': snapshot(db)}, indent=2))
else:
    with sqlite3.connect(args.backup.resolve().as_uri() + '?mode=ro', uri=True) as backup:
        before, after = snapshot(backup), snapshot(db)
    assert before == after, 'Application table contents changed during upgrade'
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    print(json.dumps({'all_tables_unchanged': True, 'integrity': 'ok', 'tables': len(after),
                      'rows': {name: value['rows'] for name, value in after.items()}}, indent=2))
