#!/usr/bin/env python3
"""Load the six verified sample responses. No network requests."""
import json
import core
core.init_db()
for entry_id in ['763', '103', '784', '777', '127', '1030']:
    if not core.get_entry(entry_id):
        raw = json.loads((core.ROOT / 'research' / f'entry-{entry_id}.json').read_text())
        core.save_entry(core.normalize(raw['data']['page']), raw_page=raw['data']['page'])
print(json.dumps(core.stats(), ensure_ascii=False))
