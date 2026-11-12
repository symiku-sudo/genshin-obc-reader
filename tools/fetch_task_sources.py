"""Cache public task pages, bounded to two downloads and the shared rate limiter."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from concurrent.futures import ThreadPoolExecutor
import core
from task_text import metadata

def main():
    root = core.ROOT / 'data/task-cache';root.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((core.ROOT/'research/tasks/catalog.json').read_text())
    items=[x for x in catalog['list'][0]['list'] if metadata(x['title'],x.get('ext',{}))['kind']]
    def get(item):
        id=str(item['content_id']);path=root/f'{id}.json'
        if path.exists():return id,'cached'
        sample=core.ROOT/f'research/tasks/entry-{id}.json'
        try:
            page=json.loads(sample.read_text()) if sample.exists() else core.upstream('genshin/wapi/entry_page',{'entry_page_id':id},static=True)['page']
            if str(page['id'])!=id or not isinstance(page.get('modules'),list):raise ValueError('invalid source')
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(page,ensure_ascii=False));tmp.replace(path)
            return id,'saved'
        except Exception as exc:return id,type(exc).__name__
    errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for n,(id,status) in enumerate(pool.map(get,items),1):
            if status not in ('cached','saved'):errors.append({'id':id,'error':status})
            if n%50==0:print(f'{n}/{len(items)} errors={len(errors)}',flush=True)
    (root/'fetch-report.json').write_text(json.dumps({'total':len(items),'errors':errors},ensure_ascii=False,indent=2));print('done',len(items),errors,flush=True)
if __name__=='__main__':main()
