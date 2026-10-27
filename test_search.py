import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(core,'DB',Path(self.tmp.name)/'db');self.p.start();core.init_db()
    def tearDown(self):self.p.stop();self.tmp.cleanup()
    def add(self,id,title,parts):
        core.save_entry({'id':str(id),'title':title,'category':'书籍','parser_version':core.PARSER_VERSION,
            'sections':[{'id':f'section-{i}','title':f'卷{i+1}','text':t,'html':'','text_type':'书籍'} for i,t in enumerate(parts)]})
    def test_phrase_preserves_spaces_and_word_mode_matches_any_order(self):
        self.add(1,'样本A',['北风与南风相遇']);self.add(2,'样本B',['北风 南风相遇']);self.add(3,'样本C',['南风遇见北风'])
        self.assertEqual(core.search('北风 南风')['total'],3)
        self.assertEqual([x['id'] for x in core.search('北风 南风',mode='phrase')['items']],['2'])
        self.assertEqual(core.search('北风与南风',mode='phrase')['total'],1)
    def test_multiple_sections_and_paragraphs_in_one_entry(self):
        self.add(1,'文本',['北风'+('甲'*250)+'北风', '另一个北风故事'])
        item=core.search('北风')['items'][0]
        self.assertEqual(len(item['matches']),3)
        self.assertEqual({x['section_title'] for x in item['matches']},{'卷1','卷2'})
        self.assertTrue(all('北风' in x['snippet'] for x in item['matches']))
        self.add(2,'段落',['第一段。\n北风到来。'])
        self.assertEqual(core.search('北风', favorite_ids=['2'])['items'][0]['matches'][0]['paragraph_index'], 1)
    def test_pagination_is_stable_and_favorites_apply_before_paging(self):
        for i in range(27):self.add(i,f'标题{i:02d}',['正文'])
        a=core.search();b=core.search(page=2)
        self.assertEqual((len(a['items']),len(b['items']),a['total']),(20,7,27))
        self.assertFalse({x['id'] for x in a['items']} & {x['id'] for x in b['items']})
        self.assertEqual(core.search(favorite_ids=['26'])['items'][0]['id'],'26')
        self.assertEqual(core.search(favorite_ids=[])['total'],0)
    def test_read_state_persistence_paging_and_updates(self):
        for i in range(27): self.add(i, f'标题{i:02d}', ['北风正文'])
        self.assertFalse(core.get_entry('26')['is_read'])
        core.set_read('26', True)
        core.set_read('25', True)
        self.assertEqual(core.search('北风', read_state='read')['total'], 2)
        self.assertEqual(core.search(read_state='unread')['total'], 25)
        self.assertEqual(len(core.search(read_state='unread',page=2)['items']), 5)
        self.assertTrue(all(x['is_read'] for x in core.search(read_state='read')['items']))
        self.assertEqual(core.search(read_state='read',favorite_ids=['26'])['total'],1)
        self.add(26, '更新后的标题', ['新的正文'])
        core.init_db()
        self.assertTrue(core.get_entry('26')['is_read'])
        core.set_read('26', False)
        self.assertEqual(core.search(read_state='read')['total'],1)
        for id,value in [('999',True),('25','true'),('../25',True)]:
            with self.assertRaises(ValueError): core.set_read(id,value)
        with self.assertRaises(ValueError): core.search(read_state='invalid')

    def test_limits_and_exact_punctuation(self):
        self.add(1,'文本',['原文 a+b [x] 100%'])
        self.assertEqual(core.search('a+b [x]',mode='phrase')['total'],1)
        for kwargs in [{'page':0},{'page_size':101},{'mode':'invalid'},{'favorite_ids':["' OR 1=1"]}]:
            with self.assertRaises(ValueError):core.search(**kwargs)

if __name__=='__main__':unittest.main()
