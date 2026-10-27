#!/usr/bin/env python3
"""Reparse only reviewed items from their saved source pages; makes no network calls."""
import hashlib,json,sys
import core,import_jobs
from text_extract import PARSER_VERSION,TextExtractionError


def recheck(job_id):
    with core.connect() as db:
        job=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not job or job['state'] not in ('completed','paused','failed'):
            raise ValueError('任务必须处于已结束或已暂停状态')
        rows=db.execute("SELECT i.entry_id,s.payload,e.payload old FROM job_items i LEFT JOIN sources s ON s.entry_id=i.entry_id LEFT JOIN entries e ON e.id=i.entry_id WHERE i.job_id=? AND i.state='review'",(job_id,)).fetchall()
    changed=[]
    for row in rows:
        if not row['payload']:
            continue
        page=json.loads(row['payload'])
        old=json.loads(row['old']) if row['old'] else {}
        try:
            entry=core.normalize(page)
            reviews=[x for x in entry['extraction'] if x['status']=='review']
            status='review' if reviews else 'success'
            details={'sections':len(entry['sections']),'review_modules':len(reviews),'offline_recheck':True}
            if entry['sections'] and not reviews:
                if old:
                    entry['fetched_at']=old.get('fetched_at',entry['fetched_at'])
                    if old.get('snapshot'):entry['snapshot']=True
                core.save_entry(entry,raw_page=page)
        except TextExtractionError as e:
            status='review' if e.needs_review else 'no_text'
            details={'sections':0,'review_modules':sum(x['status']=='review' for x in e.audit),'offline_recheck':True}
        raw_hash=hashlib.sha256(json.dumps(page,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        with core.connect() as db:
            check=db.execute('SELECT version FROM entry_checks WHERE entry_id=?',(row['entry_id'],)).fetchone()
            version=check['version'] if check else str(page.get('version') or '')
            db.execute('INSERT OR REPLACE INTO entry_checks VALUES(?,?,?,?,?,?,?)',(row['entry_id'],version,raw_hash,PARSER_VERSION,status,import_jobs.now(),json.dumps(details,ensure_ascii=False)))
            db.execute('UPDATE job_items SET state=?,error=?,details=? WHERE job_id=? AND entry_id=?',(status,'',json.dumps(details,ensure_ascii=False),job_id,row['entry_id']))
        changed.append({'id':row['entry_id'],'state':status,'sections':details['sections']})
    return changed

if __name__=='__main__':
    if len(sys.argv)<2:raise SystemExit('usage: recheck_saved_reviews.py JOB_ID [...]')
    print(json.dumps([{'job':j,'results':recheck(j)} for j in sys.argv[1:]],ensure_ascii=False,indent=2))
