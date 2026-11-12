"""Build a reviewable release candidate from a DB copy and cached public sources."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import json
import sqlite3
import time
from collections import Counter
import core
import catalog
import import_jobs
from task_text import TASK_CATEGORIES, metadata


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=core.ROOT/'data/qa-v130/candidate.sqlite3');args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.resolve()==core.DB.resolve():raise ValueError('Use a separate candidate database')
    if not args.output.exists():
        with sqlite3.connect('file:'+str(core.DB)+'?mode=ro',uri=True) as source, sqlite3.connect(args.output) as dest:source.backup(dest)
    core.DB=args.output;core.init_db();import_jobs.init_jobs()
    data=json.loads((core.ROOT/'research/tasks/catalog.json').read_text());cache=core.ROOT/'data/task-cache'
    counts=Counter();failures=[];partial=[];start=time.perf_counter()
    for kind in TASK_CATEGORIES:
        manifest=catalog.parse_manifest(data,kind)
        # Only install local directory metadata; never schedule network jobs here.
        with core.connect() as db:
            db.execute('INSERT OR REPLACE INTO catalogs VALUES(?,?)',(kind,json.dumps(manifest,ensure_ascii=False)))
            db.execute('UPDATE catalog_items SET listed=0 WHERE category=?',(kind,))
            db.executemany('INSERT OR REPLACE INTO catalog_items VALUES(?,?,?,1)',[(kind,i['id'],i['title']) for i in manifest['items']])
        for item in manifest['items']:
            path=cache/(item['id']+'.json')
            try:
                page=json.loads(path.read_text());status,details=import_jobs.check_page(item['id'],page)
                counts[(kind,status)]+=1
                if status=='review':partial.append({'id':item['id'],'kind':kind,'details':details})
            except Exception as exc:failures.append({'id':item['id'],'kind':kind,'error':str(exc)[:180]})
        print(kind,dict((s,n) for (k,s),n in counts.items() if k==kind),flush=True)
    report={'directory_total':len(data['list'][0]['list']),'classified':sum(len(catalog.parse_manifest(data,k)['items']) for k in TASK_CATEGORIES),
        'unclassified':[str(i['content_id']) for i in data['list'][0]['list'] if not metadata(i['title'],i.get('ext',{}))['kind']],
        'counts':{k:{s:n for (c,s),n in counts.items() if c==k} for k in TASK_CATEGORIES},'failures':failures,'partial':partial,'seconds':time.perf_counter()-start}
    (args.output.parent/'coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    with core.connect() as db:print('integrity',db.execute('PRAGMA integrity_check').fetchone()[0],flush=True)
    print('finished',report['seconds'],'failures',len(failures),flush=True)
if __name__=='__main__':main()
