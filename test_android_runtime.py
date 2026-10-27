"""Exercise the same transport used by the embedded Android interpreter."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import import_jobs
import android_runtime
from api_service import dispatch


class NativeAPITests(unittest.TestCase):
    def test_offline_api_and_persistence(self):
        root = core.ROOT
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'ROOT', root), patch.object(core, 'DB'), patch.object(android_runtime, '_worker', None), patch.object(core, 'upstream', side_effect=AssertionError('network forbidden')):
            try:
                android_runtime.initialize(directory, str(root))
                def call(method, path, data=None):
                    result = json.loads(android_runtime.request(method, path, json.dumps(data) if data is not None else ''))
                    self.assertEqual(result['status'], 200, result)
                    return result['data']
                call('POST', '/api/sample', {'id': '1600'})
                call('POST', '/api/read', {'id': '1600', 'is_read': True})
                self.assertTrue(call('GET', '/api/entry/1600')['is_read'])
                self.assertEqual(call('GET', '/api/search?read=read')['total'], 1)
                self.assertEqual(call('GET', '/api/search?read=unread')['total'], 0)
                self.assertEqual(call('GET', '/api/search?favorite_only=1&favorites=1600')['total'], 1)
                call('POST', '/api/reading-restore', {'read_entries': ['999']})
                self.assertEqual(set(call('GET', '/api/reading-backup')['read_entries']), {'1600', '999'})
                self.assertEqual(len(call('GET', '/api/library')['categories']), 7)
                self.assertTrue((Path(directory) / 'library.sqlite3').exists())
                self.assertEqual(call('GET', '/api/stats')['entries'], 1)
            finally:
                if android_runtime._worker:
                    android_runtime._worker.stop()
                    android_runtime._worker.thread.join(timeout=5)

    def test_native_boundary_validation(self):
        for method, path, body, status in [
            ('GET', '/api/entry/../core', b'', 404),
            ('POST', '/api/read', b'[]', 400),
            ('POST', '/api/read', b'{}' * 1000, 400),
            ('GET', '/api/search?page=no', b'', 400),
            ('DELETE', '/api/read', b'', 405),
            ('GET', '/core.py', b'', 404),
        ]:
            self.assertEqual(dispatch(method, path, body)[0], status)
