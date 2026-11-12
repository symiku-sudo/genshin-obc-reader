"""Durable, single-worker imports with explicit coverage and pause/retry semantics."""
import hashlib
import json
import threading
import uuid
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from task_text import TASK_PARSER_VERSION, is_task
from datetime import datetime, timezone
import core
import catalog
from text_extract import PARSER_VERSION, TextExtractionError

ACTIVE = ('queued', 'scanning', 'running', 'pausing')
TERMINAL_ITEMS = ('success', 'unchanged', 'no_text', 'review', 'failed')
_write_lock = threading.RLock()

LABELS = {'pending':'等待', 'processing':'处理中', 'success':'已更新', 'unchanged':'未变化', 'no_text':'无所需文本', 'review':'待适配', 'failed':'获取失败'}


def now():
    return datetime.now(timezone.utc).isoformat()


def init_jobs(recover=False):
    with core.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS catalogs(category TEXT PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS catalog_items(category TEXT,entry_id TEXT,title TEXT,listed INTEGER,
            PRIMARY KEY(category,entry_id));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,category TEXT,state TEXT,phase TEXT,
            created_at TEXT,updated_at TEXT,error TEXT DEFAULT '',manifest_digest TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS job_items(job_id TEXT,entry_id TEXT,title TEXT,state TEXT,
            attempts INTEGER DEFAULT 0,error TEXT DEFAULT '',details TEXT DEFAULT '{}',
            PRIMARY KEY(job_id,entry_id));
        CREATE INDEX IF NOT EXISTS job_queue ON job_items(job_id,state);
        CREATE TABLE IF NOT EXISTS entry_checks(entry_id TEXT PRIMARY KEY,version TEXT,raw_hash TEXT,
            parser_version INTEGER,status TEXT,checked_at TEXT,details TEXT);
        ''')
        if recover:
            db.execute("UPDATE jobs SET state='paused',updated_at=?,error='服务曾中断，可继续未完成任务' WHERE state IN ('queued','scanning','running','pausing')", (now(),))
            db.execute("UPDATE job_items SET state='pending' WHERE state='processing'")


def create_jobs(categories):
    if not isinstance(categories, list) or not categories or any(c not in catalog.CATEGORIES for c in categories):
        raise ValueError('请选择支持的分类')
    ids = []
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for category in dict.fromkeys(categories):
            existing = db.execute("SELECT id FROM jobs WHERE category=? AND state IN ('queued','scanning','running','pausing','paused') ORDER BY created_at DESC LIMIT 1", (category,)).fetchone()
            if existing:
                ids.append(existing['id']); continue
            job_id = uuid.uuid4().hex
            db.execute('INSERT INTO jobs(id,category,state,phase,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                       (job_id, category, 'queued', 'catalog', now(), now()))
            ids.append(job_id)
    return ids


def job_details(job_id, status='', page=1):
    with core.connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise ValueError('任务不存在')
        result = dict(row)
        counts = {s:0 for s in ['pending','processing',*TERMINAL_ITEMS]}
        counts.update({r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM job_items WHERE job_id=? GROUP BY state',(job_id,))})
        result.update(counts=counts, total=sum(counts.values()), done=sum(counts[s] for s in TERMINAL_ITEMS), name=catalog.CATEGORIES[row['category']][0])
        conditions, args = ['job_id=?'], [job_id]
        if status:
            if status not in counts: raise ValueError('无效状态筛选')
            conditions.append('state=?');args.append(status)
        where = ' AND '.join(conditions)
        result['item_total'] = db.execute('SELECT COUNT(*) FROM job_items WHERE '+where,args).fetchone()[0]
        rows = db.execute('SELECT * FROM job_items WHERE '+where+' ORDER BY CAST(entry_id AS INTEGER) LIMIT 40 OFFSET ?',[*args,(page-1)*40]).fetchall()
        result['items'] = [{**dict(r),'details':json.loads(r['details']), 'label':LABELS[r['state']]} for r in rows]
        result['page'] = page
        return result


def dashboard():
    with core.connect() as db:
        categories=[]
        for key,(name,_) in catalog.CATEGORIES.items():
            saved=db.execute('SELECT payload FROM catalogs WHERE category=?',(key,)).fetchone()
            manifest=json.loads(saved['payload']) if saved else None
            cached=db.execute('SELECT COUNT(*) FROM catalog_items c JOIN entries e ON e.id=c.entry_id WHERE c.category=? AND c.listed=1 AND e.parser_version=?',(key,PARSER_VERSION)).fetchone()[0]
            categories.append({'id':key,'name':name,'total':len(manifest['items']) if manifest else None,
                'cached':cached,'partial':db.execute('SELECT COUNT(*) FROM catalog_items c JOIN task_metadata t ON t.entry_id=c.entry_id WHERE c.category=? AND c.listed=1 AND t.incomplete=1',(key,)).fetchone()[0], 'fetched_at':manifest['fetched_at'] if manifest else None,
                'duplicates':manifest['duplicates'] if manifest else 0,
                'unlisted':db.execute('SELECT COUNT(*) FROM catalog_items WHERE category=? AND listed=0',(key,)).fetchone()[0]})
        ids=[r[0] for r in db.execute('SELECT id FROM jobs ORDER BY created_at DESC LIMIT 15')]
    jobs=[]
    for id in ids:
        job=job_details(id);job.pop('items');jobs.append(job)
    return {'categories':categories,'jobs':jobs,'database_bytes':core.DB.stat().st_size if core.DB.exists() else 0, 'backup_bytes':sum(p.stat().st_size for p in core.DB.parent.glob('library-before-text-*.sqlite3'))}


def action(job_id, command):
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row: raise ValueError('任务不存在')
        if command == 'pause':
            if row['state'] in ACTIVE:
                # In-flight requests finish before the worker acknowledges the pause.
                state='pausing' if row['state'] in ('running','scanning','pausing') else 'paused'
                db.execute('UPDATE jobs SET state=?,updated_at=? WHERE id=?',(state,now(),job_id))
        elif command == 'resume':
            if row['state'] not in ('paused','failed'): raise ValueError('任务当前不能继续')
            db.execute("UPDATE job_items SET state='pending' WHERE job_id=? AND state='processing'",(job_id,))
            db.execute("UPDATE jobs SET state='queued',error='',updated_at=? WHERE id=?",(now(),job_id))
        elif command in ('retry', 'recheck'):
            if row['state'] not in ('completed','paused','failed'): raise ValueError('请先暂停任务，再重试失败项')
            target = 'failed' if command == 'retry' else 'review'
            if command == 'recheck':
                db.execute("DELETE FROM entry_checks WHERE entry_id IN (SELECT entry_id FROM job_items WHERE job_id=? AND state='review')", (job_id,))
            db.execute("UPDATE job_items SET state='pending',error='' WHERE job_id=? AND state=?",(job_id,target))
            db.execute("UPDATE jobs SET state='queued',error='',updated_at=? WHERE id=?",(now(),job_id))
        else: raise ValueError('未知操作')
    return job_details(job_id)


def acknowledge_pause(job_id):
    with core.connect() as db:
        row=db.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row or row['state'] in ('paused','pausing'):
            if row and row['state']=='pausing':
                db.execute("UPDATE jobs SET state='paused',updated_at=? WHERE id=?",(now(),job_id))
            return True
    return False


def install_manifest(job_id, manifest):
    with core.connect() as db:
        category=manifest['category']
        # Snapshot and queue are committed together. A failed scan keeps the old list.
        db.execute('INSERT OR REPLACE INTO catalogs VALUES(?,?)',(category,json.dumps(manifest,ensure_ascii=False)))
        db.execute('UPDATE catalog_items SET listed=0 WHERE category=?',(category,))
        for item in manifest['items']:
            db.execute('INSERT OR REPLACE INTO catalog_items VALUES(?,?,?,1)',(category,item['id'],item['title']))
            db.execute("INSERT OR IGNORE INTO job_items(job_id,entry_id,title,state) VALUES(?,?,?,'pending')",(job_id,item['id'],item['title']))
        db.execute("UPDATE jobs SET phase='entries',manifest_digest=?,updated_at=? WHERE id=?",(manifest['digest'],now(),job_id))


def fetch_and_check(entry_id):
    page=core.upstream('genshin/wapi/entry_page',{'entry_page_id':entry_id},static=True)['page']
    with _write_lock:
        return check_page(entry_id, page)


def check_page(entry_id, page):
    if not isinstance(page, dict) or not isinstance(page.get('modules'), list) or not page.get('name'):
        raise ValueError('上游词条结构不完整，保留已有缓存')
    if str(page.get('id'))!=entry_id: raise ValueError('上游返回词条 ID 不匹配')
    version=str(page.get('version') or '')
    raw_hash=hashlib.sha256(json.dumps(page,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    cached=core.get_entry(entry_id)
    with core.connect() as db:
        previous=db.execute('SELECT * FROM entry_checks WHERE entry_id=?',(entry_id,)).fetchone()
    if previous and previous['parser_version']==PARSER_VERSION and previous['raw_hash']==raw_hash and (not is_task(page) or json.loads(previous['details']).get('task_parser_version') == TASK_PARSER_VERSION):
        status='unchanged' if previous['status']=='success' and cached and not cached.get('requires_refresh') else previous['status']
        if status != 'success':
            with core.connect() as db: db.execute('UPDATE entry_checks SET checked_at=? WHERE entry_id=?',(now(),entry_id))
            details=json.loads(previous['details']);details['unchanged']=True
            return status, details
    entry_to_save = None
    try:
        entry=core.normalize(page)
        review=[r for r in entry['extraction'] if r['status']=='review']
        status='review' if review or entry.get('incomplete') else 'success'
        details={'sections':len(entry['sections']),'review_modules':len(review),'retained_old':bool((review or entry.get('incomplete')) and cached and not cached.get('requires_refresh') and not cached.get('incomplete')), 'incomplete':bool(entry.get('incomplete'))}
        if not details['retained_old']:
            entry_to_save = entry
    except TextExtractionError as exc:
        status='review' if exc.needs_review else 'no_text'
        details={'sections':0,'review_modules':sum(r['status']=='review' for r in exc.audit),'retained_old':bool(cached)}
    if is_task(page): details['task_parser_version'] = TASK_PARSER_VERSION
    with core.connect() as db:
        if entry_to_save is not None: core.save_entry(entry_to_save, db=db)
        db.execute('INSERT OR REPLACE INTO sources VALUES(?,?)',(entry_id,json.dumps(page,ensure_ascii=False)))
        db.execute('INSERT OR REPLACE INTO entry_checks VALUES(?,?,?,?,?,?,?)',(entry_id,version,raw_hash,PARSER_VERSION,status,now(),json.dumps(details,ensure_ascii=False)))
    return status,details


class Worker:
    def __init__(self, concurrency=2):
        self.concurrency = max(1, min(4, concurrency))
        self.stop_event=threading.Event()
        self.wake=threading.Event()
        self.thread=None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.thread=threading.Thread(target=self.loop,name='text-import-worker',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set();self.wake.set()
        if self.thread: self.thread.join(timeout=25)

    def loop(self):
        while not self.stop_event.is_set():
            with core.connect() as db:
                row=db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                try: self.run_job(row['id'])
                except Exception as exc:
                    with core.connect() as db:
                        db.execute("UPDATE jobs SET state='failed',error=?,updated_at=? WHERE id=?",('任务中断：'+type(exc).__name__,now(),row['id']))
            else:
                self.wake.wait(1);self.wake.clear()

    def run_job(self, job_id):
        if acknowledge_pause(job_id): return
        with core.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state']!='queued': return
            db.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=?",('scanning' if row['phase']=='catalog' else 'running',now(),job_id))
        if row['phase']=='catalog':
            try: manifest=catalog.fetch_manifest(row['category'])
            except Exception as exc:
                with core.connect() as db:
                    db.execute("UPDATE jobs SET state='failed',error=?,updated_at=? WHERE id=?",('目录获取失败：'+str(exc)[:160],now(),job_id))
                return
            install_manifest(job_id,manifest)
        if acknowledge_pause(job_id): return
        with core.connect() as db: db.execute("UPDATE jobs SET state='running',updated_at=? WHERE id=? AND state IN ('scanning','queued')",(now(),job_id))
        # Bound outstanding work. Downloads overlap; parsing and writes serialize.
        with ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix='text-fetch') as pool:
            while not self.stop_event.is_set():
                if acknowledge_pause(job_id): return
                with core.connect() as db:
                    items=db.execute("SELECT * FROM job_items WHERE job_id=? AND state='pending' ORDER BY CAST(entry_id AS INTEGER) LIMIT ?",(job_id,self.concurrency)).fetchall()
                    if not items:
                        db.execute("UPDATE jobs SET state=CASE WHEN state='pausing' THEN 'paused' ELSE 'completed' END,updated_at=? WHERE id=?",(now(),job_id));return
                    db.executemany("UPDATE job_items SET state='processing',error='' WHERE job_id=? AND entry_id=?", [(job_id,i['entry_id']) for i in items])
                futures=[pool.submit(self.process_item, job_id, dict(item)) for item in items]
                for future in futures: future.result()
        with core.connect() as db:
            db.execute("UPDATE jobs SET state='paused',updated_at=? WHERE id=?",(now(),job_id))

    def process_item(self, job_id, item):
        status, details, error='failed',{},''
        for attempt in range(3):
            if self.stop_event.is_set(): break
            with core.connect() as db:
                state=db.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()[0]
                if state in ('paused','pausing'):
                    status='pending';break
                db.execute('UPDATE job_items SET attempts=attempts+1 WHERE job_id=? AND entry_id=?',(job_id,item['entry_id']))
            try:
                status,details=fetch_and_check(item['entry_id']);break
            except Exception as exc:
                error=str(exc)[:180] or type(exc).__name__
                if isinstance(exc, ValueError): break
                delay = 2**(attempt+1)
                if isinstance(exc, urllib.error.HTTPError) and exc.code in (429,503):
                    try: delay = max(delay, min(60, float(exc.headers.get('Retry-After', delay))))
                    except (TypeError, ValueError): pass
                if attempt<2 and self.stop_event.wait(delay): break
        with core.connect() as db:
            if self.stop_event.is_set() and status=='failed': status='pending'
            db.execute('UPDATE job_items SET state=?,error=?,details=? WHERE job_id=? AND entry_id=?',(status,error if status=='failed' else '',json.dumps(details,ensure_ascii=False),job_id,item['entry_id']))
            db.execute('UPDATE jobs SET updated_at=? WHERE id=?',(now(),job_id))
