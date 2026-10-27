"""Explicitly selected fixtures. Samples are opt-in, never bulk-added on startup."""
import json
from datetime import datetime, timezone
import core

SAMPLE_IDS = ('763', '103', '784', '777', '127', '1030', '174', '503', '625', '54', '1323', '1644', '1600')
DEMO_IDS = ('174', '1600', '625', '54', '1323')


def raw_sample(entry_id):
    if entry_id not in SAMPLE_IDS:
        raise ValueError('不是已验证的样本 ID')
    path = core.ROOT / 'research' / f'entry-{entry_id}.json'
    data = json.loads(path.read_text())
    return data['data']['page'], datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def load_sample(entry_id):
    existing = core.get_entry(entry_id)
    if existing and not existing.get('requires_refresh'):
        return existing
    page, fetched = raw_sample(entry_id)
    entry = core.normalize(page)
    entry['fetched_at'] = fetched
    entry['snapshot'] = True
    return core.save_entry(entry, raw_page=page)


def sample_list():
    items = []
    for entry_id in DEMO_IDS:
        page, fetched = raw_sample(entry_id)
        entry = core.normalize(page)
        items.append({'id': entry_id, 'category': entry['category'], 'title': entry['title'],
                      'sections': len(entry['sections']), 'fetched_at': fetched})
    return items
