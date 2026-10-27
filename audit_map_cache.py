#!/usr/bin/env python3
"""Audit saved map-text sources without network requests or story excerpts."""
import json
from collections import Counter
from datetime import datetime, timezone
import core
from text_extract import plain


def audit():
    result = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': '观测枢地图文本公开目录，不代表游戏全部零散文本',
              'listed': 0, 'source_pages': 0, 'cached': 0, 'sections': 0,
              'review': [], 'missing_text': [], 'excluded_dialogue': []}
    with core.connect() as db:
        rows = db.execute('''SELECT c.entry_id,s.payload source,e.payload entry
            FROM catalog_items c LEFT JOIN sources s ON s.entry_id=c.entry_id
            LEFT JOIN entries e ON e.id=c.entry_id
            WHERE c.category='map_texts' AND c.listed=1''').fetchall()
        result['listed'] = len(rows)
        job = db.execute("SELECT id,state FROM jobs WHERE category='map_texts' ORDER BY created_at DESC LIMIT 1").fetchone()
        if job:
            result['job'] = dict(job)
            result['job']['counts'] = dict(db.execute('SELECT state,COUNT(*) FROM job_items WHERE job_id=? GROUP BY state', (job['id'],)).fetchall())
    for row in rows:
        if not row['source']:
            continue
        result['source_pages'] += 1
        page = json.loads(row['source'])
        entry = json.loads(row['entry']) if row['entry'] else None
        if entry:
            result['cached'] += 1
            result['sections'] += len(entry['sections'])
            reviews = [r for r in entry['extraction'] if r['status']=='review']
            if reviews:
                result['review'].append({'id':row['entry_id'], 'components':[r['component'] for r in reviews]})
            for record in entry['extraction']:
                if record['component']=='interactive_dialogue' and record['status']=='excluded':
                    result['excluded_dialogue'].append({'id':row['entry_id'],'reason':record['reason']})
        expected = Counter()
        for module in page.get('modules', []):
            if module.get('is_hidden'):
                continue
            for component in module.get('components', []):
                if component.get('component_id') != 'interactive_dialogue':
                    continue
                data = component.get('data')
                data = json.loads(data) if isinstance(data, str) else data
                for tree in data.get('list') or [data]:
                    for node in (tree.get('contents') or {}).values():
                        for key in ('option','dialogue'):
                            text = plain(node.get(key))
                            if text:
                                expected[text] += 1
        actual = Counter(s['text'] for s in entry['sections'] if s['text_type']=='交互文本') if entry else Counter()
        missing = expected - actual
        if missing:
            result['missing_text'].append({'id':row['entry_id'], 'blocks':sum(missing.values()),'cached':bool(entry)})
    return result

if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
