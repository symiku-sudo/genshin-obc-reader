import copy
import html
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import sample_corpus
from rebuild_text_cache import rebuild
from text_extract import extract_page, plain


def fixture(id):
    return sample_corpus.raw_sample(id)[0]


def compact_source(value):
    """Independent text-content comparison, ignoring markup and whitespace only."""
    if isinstance(value, list):
        value = ''.join(value)
    return re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]*>', '', value)))


def compact_result(value):
    return re.sub(r'\s+', '', value)


class TextExtractionTests(unittest.TestCase):
    def test_all_thirteen_fixtures_have_only_prose_and_complete_component_audit(self):
        for id in sample_corpus.SAMPLE_IDS:
            with self.subTest(id=id):
                page = fixture(id); entry = extract_page(page)
                self.assertEqual(entry['language'], 'zh-CN')
                self.assertEqual(len(entry['extraction']), sum(len(m['components']) for m in page['modules']))
                self.assertFalse([r for r in entry['extraction'] if r['status']=='review'])
                for sec in entry['sections']:
                    self.assertTrue(sec['source_field'])
                    self.assertEqual(plain(sec['html']), sec['text'])
                    self.assertIsNone(re.search(r'<(?:table|img|iframe|audio|video|script)\b', sec['html']))

    def test_artifact_all_five_descriptions_and_stories_are_exact(self):
        for id in ['1644', '1600']:
            page = fixture(id); entry = extract_page(page)
            self.assertEqual(len(entry['sections']), 10)
            for m in page['modules']:
                for c in m['components']:
                    if c['component_id'] != 'artifact_list_v2': continue
                    data = json.loads(c['data'])
                    actual = [s for s in entry['sections'] if s['module_id']==m['id']]
                    self.assertEqual([s['text_type'] for s in actual], ['描述','故事'])
                    self.assertEqual(compact_result(actual[0]['text']), compact_source(data['desc']['value']))
                    self.assertEqual(compact_result(actual[1]['text']), compact_source(data['story']['value']))
            self.assertNotIn('2件套效果', ''.join(s['text'] for s in entry['sections']))

    def test_book_volume_order_and_every_volume_full_text(self):
        page = fixture('625'); entry = extract_page(page)
        books = [s for s in entry['sections'] if s['text_type']=='书籍']
        self.assertEqual([s['title'] for s in books], ['野猪公主·卷'+n for n in '一二三四五六七'])
        for sec in books:
            module = next(m for m in page['modules'] if m['id']==sec['module_id'])
            source = json.loads(module['components'][0]['data'])['rich_text']
            self.assertEqual(compact_result(sec['text']), compact_source(source))
        self.assertEqual(len({s['id'] for s in entry['sections']}), len(entry['sections']))

    def test_weapon_effects_are_separated_without_removing_story(self):
        entry = extract_page(fixture('174'))
        self.assertEqual([s['text_type'] for s in entry['sections']], ['描述','故事'])
        text = '\n'.join(s['text'] for s in entry['sections'])
        self.assertNotIn('精炼', text)
        self.assertNotIn('60%', text)
        self.assertNotIn('获取途径', text)
        self.assertIn('西风骑士团的重型仪式剑', text)
        raw = json.loads(fixture('174')['modules'][3]['components'][0]['data'])['rich_text']
        self.assertEqual(compact_result(entry['sections'][1]['text']), compact_source(raw))

    def test_character_chinese_voice_only_and_all_story_modules(self):
        page = fixture('54'); entry = extract_page(page)
        voices = [s for s in entry['sections'] if s['text_type']=='语音']
        self.assertEqual(len(voices), 79)
        data = next(json.loads(c['data']) for m in page['modules'] for c in m['components'] if c['component_id']=='role_voice')
        for sec, row in zip(voices, data['list'][0]['table']):
            self.assertEqual(sec['title'], row['name'])
            self.assertEqual(compact_result(sec['text']), compact_source(row['content']))
        for n in range(1,6):
            module = next(m for m in page['modules'] if m['name']=='角色故事'+str(n))
            sec = next(s for s in entry['sections'] if s['module_id']==module['id'])
            self.assertEqual(compact_result(sec['text']), compact_source(json.loads(module['components'][0]['data'])['rich_text']))
        self.assertFalse(any(r['status']=='included' and r['component'] in ['role_ascension','role_talent','map_desc'] for r in entry['extraction']))

    def test_explicit_chinese_selection_does_not_guess_from_first_tab(self):
        page = {'id':'1','name':'测试','modules':[{'id':'1','name':'配音展示','components':[{'component_id':'role_voice','data':{'list':[
            {'tab_name':'英语','table':[{'name':'English','content':'Do not import this.'}]},
            {'tab_name':'中文','table':[{'name':'问候','content':'你好。'}]},
            {'tab_name':'日语','table':[{'name':'日本語','content':'こんにちは。'}]}
        ]}}]}]}
        entry = extract_page(page)
        self.assertEqual([s['text'] for s in entry['sections']], ['你好。'])

    def test_task_every_dialogue_preserves_text_and_group_context(self):
        page = fixture('1323'); entry = extract_page(page)
        dialogues = [s for s in entry['sections'] if s['text_type']=='对白']
        self.assertEqual(len(dialogues), 5)
        for sec in dialogues:
            self.assertTrue(sec['context'])
            module = next(m for m in page['modules'] if m['id']==sec['module_id'])
            self.assertEqual(compact_result(sec['text']), compact_source(json.loads(module['components'][0]['data'])['rich_text']))
        self.assertFalse(any('奖励' in s['title'] or '攻略' in s['title'] for s in entry['sections']))

    def test_unknown_and_malformed_components_never_flatten_silently(self):
        page = {'id':'2','name':'测试','modules':[{'id':'2','name':'故事','components':[
            {'component_id':'collapse_panel','data':{'rich_text':'<p>500年前，有3位旅人。</p><p>第二段。</p>'}},
            {'component_id':'new_widget','data':{'foo':'不要悄悄加入'}},
            {'component_id':'artifact_list_v2','data':'invalid-json'}]}]}
        entry = extract_page(page)
        self.assertEqual(entry['sections'][0]['text'], '500年前，有3位旅人。\n第二段。')
        self.assertEqual([x['status'] for x in entry['extraction']], ['included','review','review'])
        self.assertEqual(len(entry['warnings']), 1)

    def test_image_only_table_is_excluded_but_text_table_needs_review(self):
        base = {'id':'2','name':'测试','modules':[{'id':'2','name':'故事','components':[
            {'component_id':'collapse_panel','data':{'rich_text':'正文'}},
            {'component_id':'multi_table','data':{'tables':[{'header':['',''],'row':[['<img src="x">','']]}]}}]}]}
        entry=extract_page(base)
        self.assertEqual(entry['extraction'][1]['status'],'excluded')
        base['modules'][0]['components'][1]['data']['tables'][0]['row']=[['正文待适配','']]
        self.assertEqual(extract_page(base)['extraction'][1]['status'],'review')

    def test_markup_never_executes_and_media_is_not_text(self):
        value = '<p>第一段<img src="https://x" alt="数值图" onerror="evil()"></p><script>evil()</script><iframe>hidden</iframe><p>第二段 &amp; 原文</p>'
        self.assertEqual(plain(value), '第一段\n第二段 & 原文')


class CacheMigrationTests(unittest.TestCase):
    def test_old_cache_is_rebuilt_offline_and_old_index_removed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core,'DB',Path(tmp)/'cache.sqlite3'):
            core.init_db()
            page = fixture('103')
            old = core.normalize(page); old.pop('parser_version')
            old['sections'][0]['text'] += '\n22%旧数值标记'
            core.save_entry(old,raw_page=page)
            with patch.object(core,'upstream',side_effect=AssertionError('must stay offline')):
                result = rebuild()
            self.assertEqual(result['updated'],['103'])
            self.assertTrue(Path(result['backup']).is_file())
            self.assertEqual(core.get_entry('103')['fetched_at'], old['fetched_at'])
            self.assertFalse(core.search('旧数值标记')['items'])
            self.assertTrue(core.search('细嫩的禽肉')['items'])
            self.assertIsNone(rebuild()['backup'])

    def test_unrecoverable_legacy_cache_is_preserved_but_not_searched(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core,'DB',Path(tmp)/'cache.sqlite3'):
            core.init_db()
            old={'id':'999999999','title':'旧数据','category':'测试','fetched_at':'old','sections':[{'id':'x','title':'属性','text':'攻击力100','html':'攻击力100'}]}
            core.save_entry(old)
            self.assertEqual(rebuild()['needs_refresh'],['999999999'])
            self.assertTrue(core.get_entry(old['id'])['requires_refresh'])
            self.assertFalse(core.get_entry(old['id'])['sections'])
            self.assertFalse(core.search('攻击力')['items'])

    def test_samples_are_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core,'DB',Path(tmp)/'cache.sqlite3'):
            core.init_db()
            self.assertTrue(sample_corpus.sample_list())
            self.assertEqual(core.stats()['entries'],0)
            with patch.object(core,'upstream',side_effect=AssertionError('offline sample')):
                sample_corpus.load_sample('625')
            self.assertEqual(core.stats()['entries'],1)
            self.assertTrue(core.get_entry('625')['snapshot'])
            with self.assertRaises(ValueError): sample_corpus.load_sample('../core.py')

if __name__ == '__main__': unittest.main()
