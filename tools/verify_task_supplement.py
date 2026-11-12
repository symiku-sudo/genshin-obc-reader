"""Validate every packaged task, including all branch targets, before APK build."""
import argparse
import gzip
import json
from collections import Counter


def verify(path):
    entries=[]
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['type']=='entry':entries.append(row['entry'])
    if not entries or len({e['id'] for e in entries})!=len(entries):raise ValueError('Empty or duplicate tasks')
    counts=Counter(e['category'] for e in entries)
    if set(counts)!={'魔神任务','世界任务','传说任务','邀约任务','限时任务'}:raise ValueError('Missing task category')
    for entry in entries:
        if 'is_read' in entry:raise ValueError('Reading flag in public corpus')
        ids={s['id'] for s in entry['sections']}
        if not ids or len(ids)!=len(entry['sections']):raise ValueError('Empty or duplicate sections: '+entry['id'])
        for section in entry['sections']:
            for link in section.get('links',[]):
                if link['id'] not in ids:raise ValueError('Broken branch target: '+entry['id']+'/'+link['id'])
    result={'tasks':len(entries),'categories':dict(counts),'partial':sum(bool(e.get('incomplete')) for e in entries),'all_branch_targets_valid':True}
    print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('path');verify(parser.parse_args().path)
