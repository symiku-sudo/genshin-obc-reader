#!/usr/bin/env python3
"""Reparse only existing cache entries; preserve snapshots and make a DB backup."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
import core
from text_extract import PARSER_VERSION


def rebuild():
    core.init_db()
    with core.connect() as db:
        rows = db.execute('SELECT id,payload FROM entries').fetchall()
    pending = [(r['id'], json.loads(r['payload'])) for r in rows if json.loads(r['payload']).get('parser_version') != PARSER_VERSION]
    if not pending:
        return {'updated': [], 'needs_refresh': [], 'backup': None}
    backup = core.DB.with_name('library-before-text-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.sqlite3')
    with core.connect() as db, closing(sqlite3.connect(backup)) as dest:
        db.backup(dest)
    result = {'updated': [], 'needs_refresh': [], 'backup': str(backup)}
    for entry_id, old in pending:
        with core.connect() as db:
            row = db.execute('SELECT payload FROM sources WHERE entry_id=?', (entry_id,)).fetchone()
        page = json.loads(row['payload']) if row else None
        fixture = core.ROOT / 'research' / f'entry-{entry_id}.json'
        if page is None and fixture.is_file():
            candidate = json.loads(fixture.read_text())['data']['page']
            if candidate.get('version') == old.get('version'):
                page = candidate
        if page is None:
            result['needs_refresh'].append(entry_id)
            continue
        try:
            entry = core.normalize(page)
        except ValueError:
            result['needs_refresh'].append(entry_id)
            continue
        entry['fetched_at'] = old['fetched_at']
        if old.get('snapshot'):
            entry['snapshot'] = True
        if all(entry.get(k) == old.get(k) for k in ('title', 'category', 'sections')):
            # Audit-only changes do not require rebuilding the identical search index.
            with core.connect() as db:
                db.execute('UPDATE entries SET payload=?,parser_version=? WHERE id=?', (json.dumps(entry, ensure_ascii=False), PARSER_VERSION, entry_id))
                db.execute('INSERT OR IGNORE INTO sources VALUES(?,?)', (entry_id, json.dumps(page, ensure_ascii=False)))
        else:
            core.save_entry(entry, raw_page=page)
        result['updated'].append(entry_id)
    return result

if __name__ == '__main__':
    print(json.dumps(rebuild(), ensure_ascii=False))
