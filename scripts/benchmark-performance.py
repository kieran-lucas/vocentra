"""Compare repository hot paths with a git revision, using synthetic data only.

Usage: python scripts/benchmark-performance.py --baseline HEAD
No app database or learner state is opened.
"""
import argparse
import json
import re
import sqlite3
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='HEAD')
    args = parser.parse_args()
    revision = subprocess.check_output(['git', 'rev-parse', args.baseline], cwd=ROOT, text=True).strip()
    source_path = 'src-tauri/src/repositories/blocks.rs'
    old = subprocess.check_output(['git', 'show', f'{revision}:{source_path}'], cwd=ROOT, text=True)
    new = (ROOT / source_path).read_text(encoding='utf-8')
    queries = [re.search(r'r#"(.*?)"#', source, re.S).group(1) for source in (old, new)]
    db = sqlite3.connect(':memory:')
    db.executescript((ROOT / 'src-tauri/migrations/0001_initial.sql').read_text())
    blocks = []
    for root in range(100):
        blocks.append((f'root-{root}', None, f'Root {root}', root, '', ''))
        for leaf in range(10):
            blocks.append((f'leaf-{root}-{leaf}', f'root-{root}', f'Leaf {leaf}', leaf, '', ''))
    blocks.extend([('empty', None, 'Empty', 0, '', ''), ('deep', 'leaf-0-0', 'Deep', 0, '', '')])
    db.executemany('INSERT INTO blocks(id,parent_id,name,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?)', blocks)
    db.executemany('''INSERT INTO vocabulary_entries(id,word,ipa,part_of_speech,vi_meaning,en_definition,
      example_meaning_en,example_meaning_vi,example_usage_en,example_usage_vi,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', [(str(i), str(i), *(['test'] * 10)) for i in range(50)])
    entries = [(f'{r}-{l}-{i}', f'leaf-{r}-{l}' if (r, l) != (0, 0) else 'deep', str(i), i % 26, '', '')
               for r in range(100) for l in range(10) for i in range(50)]
    db.executemany('INSERT INTO block_entries(id,block_id,entry_id,mastery_score,created_at,updated_at) VALUES(?,?,?,?,?,?)', entries)
    db.commit()
    optimized_db = sqlite3.connect(':memory:')
    db.backup(optimized_db)
    optimized_db.executescript((ROOT / 'src-tauri/migrations/0006_block_summary_index.sql').read_text())
    results = []
    for parent in (None, 'root-0', 'root-99', 'leaf-0-0', 'deep', 'empty', 'missing'):
        expected = db.execute(queries[0], (parent,)).fetchall()
        assert optimized_db.execute(queries[1], (parent,)).fetchall() == expected, parent
        timings = []
        for connection, query in zip((db, optimized_db), queries):
            samples = []
            for _ in range(7):
                start = time.perf_counter()
                connection.execute(query, (parent,)).fetchall()
                samples.append((time.perf_counter() - start) * 1000)
            timings.append(statistics.median(samples))
        results.append({'parent': parent, 'baseline_ms': round(timings[0], 3),
                        'optimized_ms': round(timings[1], 3), 'speedup': round(timings[0] / timings[1], 2)})
    report = {'baseline': revision, 'sqlite': sqlite3.sqlite_version, 'blocks': len(blocks),
              'memberships': len(entries), 'median_of': 7, 'results_equal': True, 'queries': results}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
