#!/usr/bin/env python3
"""Generate Android inputs from the canonical website, never maintain a UI fork."""
import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'android/app/build/generated/reader'
MODULES = ('core', 'text_extract', 'catalog', 'import_jobs', 'sample_corpus',
           'rebuild_text_cache', 'api_service', 'android_runtime', 'task_text', 'corpus_upgrade')


def prepare(corpus):
    if OUT.exists():
        shutil.rmtree(OUT)
    assets = OUT / 'assets'
    python = OUT / 'python'
    python.mkdir(parents=True)
    shutil.copytree(ROOT / 'static', assets / 'web')
    shutil.copy(ROOT / 'android/runtime.js', assets / 'web/runtime.js')
    index = assets / 'web/index.html'
    csp = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'"
    index.write_text(index.read_text().replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="'+csp+'">').replace('<script src="app.js"', '<script src="runtime.js" defer></script><script src="app.js"'))
    for module in MODULES:
        shutil.copy(ROOT / (module + '.py'), python)
    research = assets / 'resources/research'
    research.mkdir(parents=True)
    for path in (ROOT / 'research').glob('entry-*.json'):
        shutil.copy(path, research)
    shutil.copy(ROOT / 'research/moon-cards.json', research)
    task_supplement(corpus, research / 'tasks.obc')
    # AAPT treats .gz filenames specially. Keep gzip bytes under an opaque extension.
    shutil.copy(corpus, assets / 'library.obc')
    shutil.copy(corpus.with_suffix('.manifest.json'), assets / 'corpus.json')


def task_supplement(corpus, target):
    # Derive upgrade assets from the very same corpus used for fresh installations.
    with tempfile.TemporaryDirectory() as directory:
        db_path=Path(directory)/'corpus.sqlite3'
        with gzip.open(corpus,'rb') as src, db_path.open('wb') as dst: shutil.copyfileobj(src,dst)
        count=0
        with sqlite3.connect(db_path) as db, gzip.open(target,'wt',encoding='utf-8') as out:
            for payload,raw in db.execute("SELECT e.payload,s.payload FROM entries e LEFT JOIN sources s ON s.entry_id=e.id WHERE e.category IN ('魔神任务','世界任务','传说任务','邀约任务','限时任务') ORDER BY e.id"):
                entry=json.loads(payload);entry.pop('is_read',None)
                if not entry.get('task'): continue
                count+=1
                out.write(json.dumps({'type':'entry','entry':entry,'source':json.loads(raw) if raw else None},ensure_ascii=False)+'\n')
            for category,payload in db.execute('SELECT category,payload FROM catalogs'):
                if category in ('archon','world','story','hangout','event'):
                    out.write(json.dumps({'type':'catalog','manifest':json.loads(payload)},ensure_ascii=False)+'\n')

    target.with_suffix('.json').write_text(json.dumps({'entries':count}))

def snapshot(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.sqlite3')
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(temp) as dest:
            src.backup(dest)
            # Corpus distribution must not distribute personal reading flags.
            dest.execute('DELETE FROM reading_state')
            for entry_id, payload in dest.execute('SELECT id,payload FROM entries').fetchall():
                entry=json.loads(payload)
                if 'is_read' in entry:
                    entry.pop('is_read')
                    dest.execute('UPDATE entries SET payload=? WHERE id=?',(json.dumps(entry,ensure_ascii=False),entry_id))
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
