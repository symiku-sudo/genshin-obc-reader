import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core

class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(core, 'DB', Path(self.tmp.name) / 'test.db')
        self.db_patch.start(); core.init_db()
        for i in ['763', '103', '127']:
            payload = json.loads((core.ROOT / 'research' / f'entry-{i}.json').read_text())
            core.save_entry(core.normalize(payload['data']['page']))

    def tearDown(self):
        self.db_patch.stop(); self.tmp.cleanup()

    def test_body_phrase_and_section_target(self):
        results = core.search('细嫩的禽肉')['items']
        self.assertEqual(results[0]['id'], '103')
        self.assertIn('细嫩的禽肉', results[0]['snippet'])
        sec = next(s for s in core.get_entry('103')['sections'] if s['id'] == results[0]['section_id'])
        self.assertNotIn('22%', sec['text'])
        self.assertEqual(sec['text_type'], '描述')

    def test_multiterm_single_character_and_exact_title(self):
        self.assertEqual(core.search('甜甜花')['items'][0]['id'], '763')
        self.assertEqual(core.search('细嫩 蜜汁')['items'][0]['id'], '103')
        self.assertTrue(core.search('花')['items'])
        self.assertFalse(core.search('细嫩 根本不存在')['items'])
        self.assertFalse(core.search("%' OR 1=1 --")['items'])
        self.assertFalse(core.search('甜甜花', '不存在')['items'])

    def test_updates_replace_old_index(self):
        item = copy.deepcopy(core.get_entry('103'))
        item['sections'] = [{'id':'new', 'title':'新正文', 'text':'替换后的测试内容', 'html':'<p>替换后的测试内容</p>'}]
        core.save_entry(item)
        self.assertFalse(core.search('细嫩的禽肉')['items'])
        self.assertEqual(core.search('替换后的')['items'][0]['section_id'], 'new')

    def test_sanitizer_and_internal_links(self):
        source = '<p onclick="evil()">正文<script>alert(1)</script><a href="javascript:alert(1)">坏链接</a><img src="x" onerror="evil()"><a href="/ys/obc/content/763/detail">甜甜花</a><iframe src="https://x"></iframe></p>'
        body, text = core.clean(source)
        self.assertNotIn('onclick', body); self.assertNotIn('onerror', body)
        self.assertNotIn('javascript:', body); self.assertNotIn('<iframe', body)
        self.assertNotIn('alert(1)', text); self.assertIn('href="#entry/763"', body)
        self.assertIn('正文', text)

    def test_text_only_corpus_excludes_gameplay_tables(self):
        entry = core.get_entry('763')
        body = ''.join(s['html'] for s in entry['sections'])
        self.assertNotIn('<table', body)
        self.assertNotIn('<img', body)
        self.assertNotIn('料理效果', body)
        self.assertEqual(core.get_entry('127')['warnings'], [])
        self.assertEqual(core.search('细嫩', text_type='故事')['items'], [])
        self.assertEqual(core.search('细嫩', text_type='描述')['items'][0]['id'], '103')

    def test_cached_read_without_network_and_failed_refresh(self):
        with patch.object(core, 'upstream', side_effect=OSError('offline')) as fetch:
            self.assertEqual(core.import_entry('103')['title'], '甜甜花酿鸡')
            fetch.assert_not_called()
            with self.assertRaises(OSError): core.import_entry('103', refresh=True)
        self.assertEqual(core.get_entry('103')['title'], '甜甜花酿鸡')

    def test_invalid_id_and_missing_body(self):
        with self.assertRaises(ValueError): core.import_entry('../../etc/passwd')
        with self.assertRaises(ValueError): core.normalize({'id':'1','name':'空白','modules':[]})

if __name__ == '__main__': unittest.main()
