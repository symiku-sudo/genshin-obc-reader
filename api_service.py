"""Transport-independent API shared by the website and the Android runtime."""
import json
import re
import urllib.parse
import core
import import_jobs
import sample_corpus


class API:
    def __init__(self, path, body=b'', worker=None):
        self.path, self.body, self.worker = path, body, worker

    @staticmethod
    def send(status, data):
        return status, data

    def get(self):
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
            return self.send(404, {'error': '接口不存在'})
        except ValueError as exc:
            return self.send(400, {'error': str(exc)})
        except Exception:
            return self.send(502, {'error': '暂时无法读取上游，请稍后重试；本地缓存仍可使用'})

    def post(self):
        try:
            size = len(self.body)
            limit = 400000 if self.path == '/api/reading-restore' else 1024
            if not 0 < size <= limit:
                raise ValueError('请求大小无效')
            payload = json.loads(self.body)
            if not isinstance(payload, dict): raise ValueError('请求必须为 JSON 对象')
            if self.path == '/api/reading-restore':
                return self.send(200, core.merge_reading(payload.get('read_entries')))
            if self.path == '/api/read':
                return self.send(200, core.set_read(str(payload.get('id', '')), payload.get('is_read')))
            if self.path == '/api/jobs/start':
                ids = import_jobs.create_jobs(payload.get('categories'))
                if self.worker: self.worker.wake.set()
                return self.send(200, {'ids': ids})
            if self.path == '/api/jobs/action':
                result = import_jobs.action(str(payload.get('id', '')), payload.get('action'))
                if self.worker: self.worker.wake.set()
                return self.send(200, result)
            if self.path == '/api/sample':
                return self.send(200, sample_corpus.load_sample(str(payload.get('id', ''))))
            if self.path != '/api/import':
                return self.send(404, {'error': '接口不存在'})
            entry = core.import_entry(str(payload.get('id', '')), refresh=payload.get('refresh') is True)
            return self.send(200, entry)
        except (ValueError, AttributeError) as exc:
            return self.send(400, {'error': str(exc)})
        except Exception:
            return self.send(502, {'error': '导入失败，上游暂时不可用；已有缓存未删除'})


def dispatch(method, path, body=b'', worker=None):
    if not path.startswith('/api/'):
        return 404, {'error': '接口不存在'}
    api = API(path, body, worker)
    if method == 'GET':
        return api.get()
    if method == 'POST':
        return api.post()
    return 405, {'error': '不支持的请求方法'}
