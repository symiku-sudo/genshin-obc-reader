import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import core
import import_jobs
from server import Handler

class QuietHandler(Handler):
    def log_message(self, *args): pass

class HTTPTests(unittest.TestCase):
    def test_text_sample_import_filter_and_security_over_http(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core, 'DB', Path(tmp)/'http.sqlite3'):
            core.init_db()
            import_jobs.init_jobs()
            server = ThreadingHTTPServer(('127.0.0.1',0), QuietHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            def request(path, body=None, headers=None):
                data = json.dumps(body).encode() if body is not None else None
                hdr = {'Content-Type':'application/json'} if body is not None else {}
                hdr.update(headers or {})
                with urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers=hdr),timeout=5) as response:
                    return response.read()
            try:
                self.assertIn('中文文本'.encode(),request('/'))
                self.assertIn(b'text-type',request('/app.js'))
                self.assertEqual(len(json.loads(request('/api/samples'))['items']),5)
                self.assertEqual(json.loads(request('/api/stats'))['entries'],0)
                self.assertEqual(len(json.loads(request('/api/library'))['categories']),7)
                created=json.loads(request('/api/jobs/start',{'categories':['books']}))
                job_id=created['ids'][0]
                self.assertEqual(json.loads(request('/api/job?id='+job_id))['state'],'queued')
                paused=json.loads(request('/api/jobs/action',{'id':job_id,'action':'pause'}))
                self.assertEqual(paused['state'],'paused')
                with patch.object(core,'upstream',side_effect=AssertionError('offline test')):
                    entry = json.loads(request('/api/sample',{'id':'1600'}))
                    self.assertEqual(len(entry['sections']),10)
                    cached = json.loads(request('/api/entry/1600'))
                    self.assertEqual(cached['language'],'zh-CN')
                    self.assertFalse(cached['is_read'])
                    self.assertTrue(json.loads(request('/api/read',{'id':'1600','is_read':True}))['is_read'])
                    self.assertTrue(json.loads(request('/api/entry/1600'))['is_read'])
                    self.assertEqual(json.loads(request('/api/search?read=unread'))['total'],0)
                    self.assertEqual(json.loads(request('/api/search?read=read'))['total'],1)
                    request('/api/read',{'id':'1600','is_read':False})
                    request('/api/reading-restore',{'read_entries':['1600','999']})
                    self.assertEqual(set(json.loads(request('/api/reading-backup'))['read_entries']),{'1600','999'})
                    request('/api/read',{'id':'1600','is_read':False})
                    result = json.loads(request('/api/search?type='+urllib.parse.quote('故事')))
                    self.assertEqual(result['items'][0]['text_type'],'故事')
                    self.assertIn('matches',result['items'][0])
                    self.assertEqual(result['page_size'],20)
                    self.assertEqual(json.loads(request('/api/search?type='+urllib.parse.quote('语音')))['items'],[])
                for path,body,headers,expected in [('/api/sample',{'id':'1600'},{'Origin':'https://example.com'},403),('/api/sample',{'id':'../core'},None,400),('/../core.py',None,None,404),('/api/stats',None,{'Host':'example.com'},403)]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request(path,body,headers)
                    self.assertEqual(error.exception.code,expected)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)

if __name__ == '__main__': unittest.main()
