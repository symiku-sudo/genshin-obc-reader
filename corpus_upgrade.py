"""Merge a bundled task supplement without replacing newer local prose or user records."""
import gzip
import hashlib
import json
from pathlib import Path
import core


def should_replace(old, incoming):
    if old is None: return True
    # Only verified epoch-like source revisions are comparable. Unknown means keep local.
    a,b=str(old.get('version') or ''),str(incoming.get('version') or '')
    if not (a.isdigit() and b.isdigit() and len(a)>=10 and len(b)>=10): return False
    if int(b)<=int(a): return False
    if incoming.get('incomplete') and not old.get('incomplete'): return False
    return True


def install(path=None, progress=None):
    path=Path(path) if path else core.ROOT/'research/tasks.obc'
    if not path.exists(): return {'installed':0,'kept':0}
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with core.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS installed_corpora(digest TEXT PRIMARY KEY)')
        if db.execute('SELECT 1 FROM installed_corpora WHERE digest=?',(digest,)).fetchone():
            return {'installed':0,'kept':0,'already_installed':True}
    installed=kept=0
    metadata=path.with_suffix('.json')
    total=json.loads(metadata.read_text()).get('entries',0) if metadata.exists() else 0
    if progress: progress(0,total)
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['type']=='entry':
                entry=row['entry'];old=core.get_entry(entry['id']);source=row.get('source')
                reparse_same_source=False
                if old and source and str(old.get('version') or '').isdigit() and len(str(old.get('version'))) >= 10 and old.get('version') == entry.get('version') and old.get('task_parser_version',0) < entry.get('task_parser_version',0):
                    with core.connect() as db:
                        saved=db.execute('SELECT payload FROM sources WHERE entry_id=?',(entry['id'],)).fetchone()
                    reparse_same_source=bool(saved and json.loads(saved[0]) == source)
                if should_replace(old,entry) or reparse_same_source:
                    with core.connect() as db:
                        core.save_entry(entry,raw_page=source,db=db)
                        if source:
                            details={'sections':len(entry['sections']),'incomplete':bool(entry.get('incomplete')), 'task_parser_version':entry.get('task_parser_version')}
                            raw_hash=hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                            db.execute('INSERT OR REPLACE INTO entry_checks VALUES(?,?,?,?,?,?,?)',(entry['id'],str(entry.get('version') or ''),raw_hash,entry['parser_version'],'review' if entry.get('incomplete') else 'success',entry['fetched_at'],json.dumps(details)))
                    installed+=1
                else: kept+=1
                if progress: progress(installed+kept,total)
            elif row['type']=='catalog':
                m=row['manifest']
                with core.connect() as db:
                    # Live catalogs may be newer; never roll them back during upgrade.
                    saved=db.execute('SELECT payload FROM catalogs WHERE category=?',(m['category'],)).fetchone()
                    if saved and json.loads(saved[0]).get('fetched_at','') >= m['fetched_at']: continue
                    db.execute('INSERT OR REPLACE INTO catalogs VALUES(?,?)',(m['category'],json.dumps(m,ensure_ascii=False)))
                    db.execute('UPDATE catalog_items SET listed=0 WHERE category=?',(m['category'],))
                    db.executemany('INSERT OR REPLACE INTO catalog_items VALUES(?,?,?,1)',[(m['category'],i['id'],i['title']) for i in m['items']])
    # Mark only after the whole merge succeeds; interruption is safe to repeat.
    with core.connect() as db:db.execute('INSERT OR IGNORE INTO installed_corpora VALUES(?)',(digest,))
    return {'installed':installed,'kept':kept}
