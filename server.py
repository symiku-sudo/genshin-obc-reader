#!/usr/bin/env python3
import argparse
import json
import mimetypes
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import core
from api_service import dispatch
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
        if u.path.startswith('/api/'):
            return self.send(*dispatch('GET', self.path))
        file = STATIC / ('index.html' if u.path == '/' else u.path.lstrip('/'))
        if file.resolve().parent != STATIC.resolve() or not file.is_file():
            return self.send(404, {'error': '页面不存在'})
        mime = mimetypes.guess_type(file)[0] or 'application/octet-stream'
        self.send(200, file.read_bytes(), mime + ('; charset=utf-8' if mime.startswith('text/') else ''))

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
            return self.send(*dispatch('POST', self.path, self.rfile.read(size), getattr(self.server, 'worker', None)))
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
