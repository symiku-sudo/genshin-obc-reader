#!/usr/bin/env python3
"""Generate Android inputs from the canonical website, never maintain a UI fork."""
import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'android/app/build/generated/reader'
MODULES = ('core', 'text_extract', 'catalog', 'import_jobs', 'sample_corpus',
           'rebuild_text_cache', 'api_service', 'android_runtime')


def prepare(corpus):
    if OUT.exists():
        shutil.rmtree(OUT)
    assets = OUT / 'assets'
    python = OUT / 'python'
    python.mkdir(parents=True)
    shutil.copytree(ROOT / 'static', assets / 'web')
    shutil.copy(ROOT / 'android/runtime.js', assets / 'web/runtime.js')
    index = assets / 'web/index.html'
    index.write_text(index.read_text().replace('<script src="app.js"', '<script src="runtime.js" defer></script><script src="app.js"'))
    for module in MODULES:
        shutil.copy(ROOT / (module + '.py'), python)
    research = assets / 'resources/research'
    research.mkdir(parents=True)
    for path in (ROOT / 'research').glob('entry-*.json'):
        shutil.copy(path, research)
    shutil.copy(corpus, assets / 'library.sqlite3.gz')
    shutil.copy(corpus.with_suffix('.manifest.json'), assets / 'corpus.json')


def snapshot(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.sqlite3')
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(temp) as dest:
            src.backup(dest)
            # Corpus distribution must not distribute personal reading flags.
            dest.execute('DELETE FROM reading_state')
            dest.commit()
            dest.execute('VACUUM')
            assert dest.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            counts = {table: dest.execute('SELECT count(*) FROM '+table).fetchone()[0]
                      for table in ('entries', 'sections')}
        digest = hashlib.sha256()
        with temp.open('rb') as src, gzip.open(target, 'wb', compresslevel=6) as dst:
            while block := src.read(1024 * 1024):
                digest.update(block)
                dst.write(block)
        target.with_suffix('.manifest.json').write_text(json.dumps({
            **counts, 'sha256': digest.hexdigest(), 'bytes': temp.stat().st_size}, indent=2))
    finally:
        temp.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--corpus', type=Path, default=ROOT / 'data/android/library.sqlite3.gz')
    args = parser.parse_args()
    if args.snapshot:
        snapshot(ROOT / 'data/library.sqlite3', args.corpus)
    prepare(args.corpus)
