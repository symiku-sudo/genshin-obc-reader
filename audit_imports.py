#!/usr/bin/env python3
"""Read-only coverage report for each supported public catalog; no story excerpts."""
import json
from collections import Counter
from datetime import datetime, timezone
import core
import catalog
from text_extract import PARSER_VERSION


def audit():
    report = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'parser_version': PARSER_VERSION, 'categories': [],
              'scope': '原站当前公开分类目录；无所需文本、待适配和失败不算完整提取'}
    with core.connect() as db:
        for key, (name, channel) in catalog.CATEGORIES.items():
            latest = db.execute('SELECT id,state FROM jobs WHERE category=? ORDER BY created_at DESC LIMIT 1', (key,)).fetchone()
            if not latest: continue
            counts = dict(db.execute('SELECT state,COUNT(*) FROM job_items WHERE job_id=? GROUP BY state', (latest['id'],)).fetchall())
            rows = db.execute('''SELECT c.entry_id,s.payload source,e.payload entry FROM catalog_items c
                LEFT JOIN sources s ON s.entry_id=c.entry_id LEFT JOIN entries e ON e.id=c.entry_id
                WHERE c.category=? AND c.listed=1''', (key,)).fetchall()
            item = {'category':key,'name':name,'channel':channel,'job':dict(latest),'counts':counts,
                    'listed':len(rows),'cached':0,'sections':0,'review_components':{},'issues':[]}
            reasons = Counter()
            for row in rows:
                if not row['entry']: continue
                entry = json.loads(row['entry'])
                if entry['parser_version'] != PARSER_VERSION: continue
                item['cached'] += 1
                item['sections'] += len(entry['sections'])
                for record in entry.get('extraction',[]):
                    if record['status']=='review': reasons[record['component']+':'+record['reason']] += 1
            item['review_components'] = dict(reasons)
            item['issues'] = [dict(r) for r in db.execute("SELECT entry_id,state,error,details FROM job_items WHERE job_id=? AND state IN ('review','failed','no_text') ORDER BY CAST(entry_id AS INTEGER)",(latest['id'],))]
            item['complete_extraction'] = latest['state']=='completed' and not any(counts.get(s,0) for s in ('pending','processing','review','failed'))
            report['categories'].append(item)
    return report

if __name__ == '__main__':
    print(json.dumps(audit(),ensure_ascii=False,indent=2))
