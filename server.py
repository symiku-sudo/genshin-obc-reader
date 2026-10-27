#!/usr/bin/env python3
import argparse
import json
import mimetypes
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import core
import sample_corpus
import import_jobs

STATIC = Path(__file__).resolve().parent / 'static'

class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, content_type='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: http:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': '仅允许本机访问'})
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        query = q.get('q', [''])[0].strip()
        if len(query) > 100:
            return self.send(400, {'error': '搜索词请控制在 100 字以内'})
        try:
            if u.path == '/api/reading-backup':
                return self.send(200, core.reading_backup())
            if u.path == '/api/library':
                return self.send(200, import_jobs.dashboard())
            if u.path == '/api/job':
                page = int(q.get('page', ['1'])[0])
                if not 1 <= page <= 10000: raise ValueError('页码超出范围')
                return self.send(200, import_jobs.job_details(q.get('id', [''])[0], q.get('state', [''])[0], page))
            if u.path == '/api/samples':
                return self.send(200, {'items': sample_corpus.sample_list()})
            if u.path == '/api/stats':
                return self.send(200, core.stats())
            if u.path == '/api/search':
                favorites = [x for x in q.get('favorites', [''])[0].split(',') if x] if q.get('favorite_only', ['0'])[0] == '1' else None
                return self.send(200, core.search(query, q.get('category', [''])[0], q.get('type', [''])[0], mode=q.get('mode', ['all'])[0], page=int(q.get('page', ['1'])[0]), favorite_ids=favorites, read_state=q.get('read', ['all'])[0]))
            if u.path == '/api/remote':
                if not query:
                    return self.send(400, {'error': '请输入在线搜索词'})
                page = int(q.get('page', ['1'])[0])
                if not 1 <= page <= 100:
                    raise ValueError('页码超出范围')
                return self.send(200, {'items': core.remote_search(query, page)})
            if re.fullmatch(r'/api/entry/\d{1,12}', u.path):
                entry = core.get_entry(u.path.rsplit('/', 1)[1])
                return self.send(200 if entry else 404, entry or {'error': '词条尚未缓存'})
            file = STATIC / ('index.html' if u.path == '/' else u.path.lstrip('/'))
            if file.resolve().parent != STATIC.resolve() or not file.is_file():
                return self.send(404, {'error': '页面不存在'})
            mime = mimetypes.guess_type(file)[0] or 'application/octet-stream'
            self.send(200, file.read_bytes(), mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
        except ValueError as exc:
            self.send(400, {'error': str(exc)})
        except Exception:
            self.send(502, {'error': '暂时无法读取上游，请稍后重试；本地缓存仍可使用'})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin', '') not in ('', 'http://' + self.headers.get('Host', '')):
            return self.send(403, {'error': '不接受跨站请求'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': '需要 JSON 请求'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            limit = 400000 if self.path == '/api/reading-restore' else 1024
            if not 0 < size <= limit:
                raise ValueError('请求大小无效')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict): raise ValueError('请求必须为 JSON 对象')
            if self.path == '/api/reading-restore':
                return self.send(200, core.merge_reading(payload.get('read_entries')))
            if self.path == '/api/read':
                return self.send(200, core.set_read(str(payload.get('id', '')), payload.get('is_read')))
            if self.path == '/api/jobs/start':
                ids = import_jobs.create_jobs(payload.get('categories'))
                if getattr(self.server, 'worker', None): self.server.worker.wake.set()
                return self.send(200, {'ids': ids})
            if self.path == '/api/jobs/action':
                result = import_jobs.action(str(payload.get('id', '')), payload.get('action'))
                if getattr(self.server, 'worker', None): self.server.worker.wake.set()
                return self.send(200, result)
            if self.path == '/api/sample':
                return self.send(200, sample_corpus.load_sample(str(payload.get('id', ''))))
            if self.path != '/api/import':
                return self.send(404, {'error': '接口不存在'})
            entry = core.import_entry(str(payload.get('id', '')), refresh=payload.get('refresh') is True)
            self.send(200, entry)
        except (ValueError, AttributeError) as exc:
            self.send(400, {'error': str(exc)})
        except Exception:
            self.send(502, {'error': '导入失败，上游暂时不可用；已有缓存未删除'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    core.init_db()
    from rebuild_text_cache import rebuild
    migration = rebuild()
    if migration['needs_refresh']:
        print('部分旧缓存缺少原始数据，需要在原词条更新缓存：' + str(migration['needs_refresh']), flush=True)
    import_jobs.init_jobs(recover=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.worker = import_jobs.Worker()
    server.worker.start()
    print(f'观测阅读室：http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.worker.stop()
        server.server_close()
