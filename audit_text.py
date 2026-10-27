#!/usr/bin/env python3
"""Generate a spoiler-free extraction manifest from the fixed source snapshots."""
import hashlib
import json
from datetime import datetime, timezone
import core
import sample_corpus


def audit():
    results = []
    for id in sample_corpus.SAMPLE_IDS:
        page, fetched = sample_corpus.raw_sample(id)
        entry = core.normalize(page)
        raw = (core.ROOT / 'research' / f'entry-{id}.json').read_bytes()
        results.append({
            'id': id, 'category': entry['category'], 'source': entry['source'], 'source_version': entry['version'],
            'snapshot_at': fetched, 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'sections': len(entry['sections']), 'characters': sum(len(s['text']) for s in entry['sections']),
            'types': {t:sum(s['text_type']==t for s in entry['sections']) for t in sorted({s['text_type'] for s in entry['sections']})},
            'components': entry['extraction'],
        })
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'mode':'zh-prose', 'parser_version':core.PARSER_VERSION,
              'samples':len(results), 'sections':sum(x['sections'] for x in results),
              'characters':sum(x['characters'] for x in results),
              'review_components':sum(c['status']=='review' for x in results for c in x['components']),
              'scope':'Selected prose fields from these snapshots; not a claim of full-site coverage.', 'entries':results}
    path=core.ROOT/'research'/'text-audit.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return {k:v for k,v in report.items() if k!='entries'}

if __name__ == '__main__': print(json.dumps(audit(), ensure_ascii=False))
