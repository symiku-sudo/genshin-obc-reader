"""Read-only upstream adapter and local, independently searchable corpus."""
import html
import json
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from text_extract import PARSER_VERSION

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'library.sqlite3'
SOURCE = 'https://baike.mihoyo.com/ys/obc/'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': SOURCE, 'x-rpc-wiki_app': 'genshin'}
_lock = threading.Lock()
_last_request = 0.0


def upstream(path, params, static=False):
    return upstream_request('/hoyowiki/' + path, {'app_sn': 'ys_obc', **params}, static)


def upstream_request(path, params, static=False):
    global _last_request
    host = 'act-api-takumi-static.mihoyo.com' if static else 'act-api-takumi.mihoyo.com'
    url = 'https://' + host + path + '?' + urllib.parse.urlencode(params)
    with _lock:
        time.sleep(max(0, .5 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as response:
            raw = response.read(12_000_001)
    if len(raw) > 12_000_000:
        raise ValueError('上游词条过大，暂不导入')
    result = json.loads(raw)
    if result.get('retcode') != 0:
        raise ValueError('上游返回错误：' + str(result.get('message', result.get('retcode'))))
    return result['data']


def safe_url(value):
    u = urllib.parse.urljoin(SOURCE, value)
    p = urllib.parse.urlsplit(u)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        return ''
    return u


class CleanHTML(HTMLParser):
    allowed = set('p br div span strong b em i u s h2 h3 h4 ul ol li table thead tbody tr th td blockquote a img hr sup sub'.split())
    blocked = {'script', 'style', 'iframe', 'object', 'svg', 'math', 'template'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.text, self.stack = [], [], []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.skip += 1
            return
        if self.skip or tag not in self.allowed:
            return
        attrs = dict(attrs)
        out = ''
        if tag == 'a':
            url = safe_url(attrs.get('href', '')) if attrs.get('href') else ''
            p = urllib.parse.urlsplit(url)
            match = re.fullmatch(r'/ys/obc/content/(\d+)/detail/?', p.path)
            if p.hostname == 'baike.mihoyo.com' and match:
                url = '#entry/' + match[1]
            if url:
                out = ' href="' + html.escape(url, quote=True) + '"'
                if not url.startswith('#'):
                    out += ' target="_blank" rel="noopener noreferrer"'
        if tag == 'img':
            url = safe_url(attrs.get('src', '')) if attrs.get('src') else ''
            if not url:
                return
            out = ' src="' + html.escape(url, quote=True) + '" loading="lazy" referrerpolicy="no-referrer" alt="' + html.escape(attrs.get('alt', ''), quote=True) + '"'
        if tag in ('td', 'th'):
            for key in ('colspan', 'rowspan'):
                if attrs.get(key, '').isdigit() and 0 < int(attrs[key]) < 100:
                    out += f' {key}="{attrs[key]}"'
        self.out.append('<' + tag + out + '>')
        if tag not in ('br', 'img', 'hr'):
            self.stack.append(tag)
        if tag in ('p', 'br', 'div', 'tr', 'li', 'h2', 'h3', 'td', 'th'):
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag in self.blocked:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.out.append('</' + current + '>')
                if current == tag:
                    break
        if tag in ('p', 'div', 'tr', 'li', 'td', 'th'):
            self.text.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data))
            self.text.append(data)

    def finish(self):
        while self.stack:
            self.out.append('</' + self.stack.pop() + '>')
        return ''.join(self.out), re.sub(r'\n[ \t\n]*', '\n', ''.join(self.text)).strip()


def clean(value):
    parser = CleanHTML()
    parser.feed(str(value).replace('\\"', '"'))
    return parser.finish()


def normalize(page):
    from text_extract import extract_page
    return extract_page(page)


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY, title TEXT, category TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS sources(entry_id TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE IF NOT EXISTS reading_state(entry_id TEXT PRIMARY KEY, read_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sections(entry_id TEXT, section_id TEXT, title TEXT, text TEXT, PRIMARY KEY(entry_id,section_id));
        CREATE TABLE IF NOT EXISTS grams(gram TEXT, entry_id TEXT, section_id TEXT, PRIMARY KEY(gram,entry_id,section_id));
        CREATE INDEX IF NOT EXISTS sections_entry ON sections(entry_id);''')
        if 'parser_version' not in {r[1] for r in db.execute('PRAGMA table_info(entries)')}:
            db.execute('ALTER TABLE entries ADD COLUMN parser_version INTEGER DEFAULT 0')
        if 'text_type' not in {r[1] for r in db.execute('PRAGMA table_info(sections)')}:
            db.execute("ALTER TABLE sections ADD COLUMN text_type TEXT DEFAULT '描述'")


def grams(text):
    t = text.casefold()
    return {t[i:i+2] for i in range(len(t)-1) if not any(c.isspace() for c in t[i:i+2])}


def save_entry(entry, raw_page=None):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO entries(id,title,category,payload,parser_version) VALUES(?,?,?,?,?)', (entry['id'], entry['title'], entry['category'], json.dumps(entry, ensure_ascii=False), entry.get('parser_version', 0)))
        if raw_page is not None:
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?)', (entry['id'], json.dumps(raw_page, ensure_ascii=False)))
        db.execute('DELETE FROM sections WHERE entry_id=?', (entry['id'],))
        db.execute('DELETE FROM grams WHERE entry_id=?', (entry['id'],))
        for sec in entry['sections']:
            db.execute('INSERT INTO sections(entry_id,section_id,title,text,text_type) VALUES(?,?,?,?,?)', (entry['id'], sec['id'], sec['title'], sec['text'], sec.get('text_type', '描述')))
            db.executemany('INSERT INTO grams VALUES(?,?,?)', [(g, entry['id'], sec['id']) for g in grams(entry['title'] + '\n' + sec['title'] + '\n' + sec['text'])])
    entry['is_read'] = is_read(entry['id'])
    return entry


def get_entry(entry_id):
    with connect() as db:
        row = db.execute('SELECT payload FROM entries WHERE id=?', (entry_id,)).fetchone()
    if not row:
        return None
    entry = json.loads(row['payload'])
    entry['is_read'] = is_read(entry_id)
    if entry.get('parser_version') != PARSER_VERSION:
        entry['sections'] = []
        entry['warnings'] = ['旧缓存需更新为中文文本版；点击更新缓存后阅读。']
        entry['requires_refresh'] = True
    return entry


def is_read(entry_id):
    with connect() as db:
        return db.execute('SELECT 1 FROM reading_state WHERE entry_id=?', (entry_id,)).fetchone() is not None


def set_read(entry_id, value):
    if not re.fullmatch(r'\d{1,12}', str(entry_id)) or not isinstance(value, bool):
        raise ValueError('阅读状态无效')
    with connect() as db:
        if not db.execute('SELECT 1 FROM entries WHERE id=?', (entry_id,)).fetchone():
            raise ValueError('词条尚未缓存')
        if value:
            db.execute("INSERT OR REPLACE INTO reading_state VALUES(?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (entry_id,))
        else:
            db.execute('DELETE FROM reading_state WHERE entry_id=?', (entry_id,))
    return {'id':str(entry_id), 'is_read':value}


def reading_backup():
    with connect() as db:
        return {'read_entries':[r[0] for r in db.execute('SELECT entry_id FROM reading_state ORDER BY entry_id')]}


def merge_reading(ids):
    if not isinstance(ids, list) or len(ids) > 20000 or any(not isinstance(i,str) or not re.fullmatch(r'\d{1,12}', i) for i in ids):
        raise ValueError('备份中的已读记录无效')
    with connect() as db:
        db.executemany("INSERT OR IGNORE INTO reading_state VALUES(?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", ((i,) for i in set(ids)))
    return {'merged':len(set(ids))}


def import_entry(entry_id, refresh=False):
    if not re.fullmatch(r'[0-9]{1,12}', str(entry_id)):
        raise ValueError('词条 ID 格式错误')
    cached = get_entry(entry_id)
    if cached and not refresh and not cached.get('requires_refresh'):
        return cached
    page = upstream('genshin/wapi/entry_page', {'entry_page_id': entry_id}, static=True)['page']
    if str(page.get('id')) != str(entry_id):
        raise ValueError('上游返回的词条 ID 不匹配')
    return save_entry(normalize(page), raw_page=page)


def remote_search(query, page=1):
    data = upstream('wapi/search', {'keyword': query, 'menu_id': '', 'page_num': page, 'page_size': 20})
    return [{'id': x['entry_page_id'], 'title': clean(x['name'])[1], 'category': ' / '.join(m['name'] for m in (x.get('menus') or [])) or '未分类'} for x in data.get('list', [])]


def make_snippets(body, terms, limit=3):
    positions = sorted({m.start() for t in terms for m in re.finditer(re.escape(t), body.casefold())})
    if not positions: return [{'text':body[:180], 'paragraph_index':0}]
    snippets, end = [], -1
    for position in positions:
        if position < end: continue
        start = max(0, position - 45)
        end = min(len(body), start + 180)
        snippets.append({'text':('…' if start else '') + body[start:end] + ('…' if end < len(body) else ''), 'paragraph_index':body[:position].count('\n')})
        if len(snippets) >= limit: break
    return snippets


def search(query='', category='', text_type='', mode='all', page=1, page_size=20, favorite_ids=None, read_state='all'):
    if read_state not in ('all', 'read', 'unread'): raise ValueError('无效的阅读状态')
    if mode not in ('all', 'phrase'): raise ValueError('无效的搜索模式')
    if not 1 <= page <= 10000 or not 1 <= page_size <= 100: raise ValueError('无效的分页参数')
    terms = [query.casefold().strip()] if mode == 'phrase' and query.strip() else list(dict.fromkeys(query.casefold().split()))
    constraints = set().union(*(grams(t) for t in terms))
    with connect() as db:
        sql = 'SELECT s.*,e.title AS entry_title,e.category,(r.entry_id IS NOT NULL) AS is_read FROM sections s JOIN entries e ON e.id=s.entry_id LEFT JOIN reading_state r ON r.entry_id=e.id'
        args, filters = [PARSER_VERSION], ['e.parser_version=?']
        if constraints:
            marks = ','.join('?' for _ in constraints)
            filters.append(f'(s.entry_id,s.section_id) IN (SELECT entry_id,section_id FROM grams WHERE gram IN ({marks}) GROUP BY entry_id,section_id HAVING COUNT(*)=?)')
            args.extend(sorted(constraints)); args.append(len(constraints))
        if read_state == 'read': filters.append('r.entry_id IS NOT NULL')
        if read_state == 'unread': filters.append('r.entry_id IS NULL')
        if category: filters.append('e.category=?'); args.append(category)
        if text_type: filters.append('s.text_type=?'); args.append(text_type)
        if favorite_ids is not None:
            if len(favorite_ids) > 1000 or any(not re.fullmatch(r'\d{1,12}', str(i)) for i in favorite_ids):
                raise ValueError('收藏列表无效或过长')
            if not favorite_ids: return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}
            filters.append('e.id IN (' + ','.join('?' for _ in favorite_ids) + ')'); args.extend(favorite_ids)
        sql += ' WHERE ' + ' AND '.join(filters) + ' ORDER BY e.id,s.rowid'
        rows = db.execute(sql, args).fetchall()
    found = {}
    for row in rows:
        haystack = (row['entry_title'] + '\n' + row['title'] + '\n' + row['text']).casefold()
        if not all(t in haystack for t in terms): continue
        score = 100 if query and query.casefold() == row['entry_title'].casefold() else 0
        score += sum(20 for t in terms if t in row['entry_title'].casefold())
        score += sum(3 for t in terms if t in row['title'].casefold())
        hits = [{'section_id': row['section_id'], 'section_title': row['title'], 'text_type': row['text_type'], 'snippet': snippet['text'], 'paragraph_index': snippet['paragraph_index'], 'score': score} for snippet in make_snippets(row['text'], terms)]
        item = found.setdefault(row['entry_id'], {'id': row['entry_id'], 'title': row['entry_title'], 'category': row['category'], 'is_read': bool(row['is_read']), 'score': score, 'matches': [], 'match_count': 0})
        item['match_count'] += len(hits)
        item['score'] = max(item['score'], score)
        item['matches'].extend(hits)
    results = sorted(found.values(), key=lambda x: (-x['score'], x['title'], x['id']))
    start=(page-1)*page_size
    selected=results[start:start+page_size]
    for item in selected:
        item['matches'].sort(key=lambda x:-x['score'])
        item['matches']=item['matches'][:12]
        item.update({k:item['matches'][0][k] for k in ('section_id','section_title','text_type','snippet')})
    return {'items': selected, 'total': len(results), 'page': page, 'page_size': page_size}


def stats():
    with connect() as db:
        return {
            'entries': db.execute('SELECT COUNT(*) FROM entries WHERE parser_version=?', (PARSER_VERSION,)).fetchone()[0],
            'sections': db.execute('SELECT COUNT(*) FROM sections s JOIN entries e ON e.id=s.entry_id WHERE e.parser_version=?', (PARSER_VERSION,)).fetchone()[0],
            'categories': [r[0] for r in db.execute('SELECT DISTINCT category FROM entries WHERE parser_version=? ORDER BY category', (PARSER_VERSION,))],
            'text_types': [r[0] for r in db.execute('SELECT DISTINCT text_type FROM sections s JOIN entries e ON e.id=s.entry_id WHERE e.parser_version=? ORDER BY text_type', (PARSER_VERSION,))],
        }
