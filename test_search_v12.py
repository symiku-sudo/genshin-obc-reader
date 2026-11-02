import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import android_runtime
import catalog
from api_service import dispatch

class SearchV12Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.dbpatch=patch.object(core,'DB',Path(self.temp.name)/'library.sqlite3');self.dbpatch.start();core.init_db()
        for id,parts in [('1',['北风先来。\n高塔仍在。']),('2',['北风先来。','高塔仍在。']),('3',['太阳出现。']),('4',['月光照耀。'])]:
            core.save_entry({'id':id,'title':'测试'+id,'category':'书籍','parser_version':core.PARSER_VERSION,'sections':[{'id':'section-'+str(i),'title':'章节'+str(i),'text':text,'html':'','text_type':'故事'} for i,text in enumerate(parts)]})
    def tearDown(self):self.dbpatch.stop();self.temp.cleanup()
    def ids(self,**kwargs):return {x['id'] for x in core.search(**kwargs)['items']}
    def test_any_all_and_single_character(self):
        self.assertEqual(self.ids(keywords=['北风','高塔'],mode='all'),{'1'})
        self.assertEqual(self.ids(keywords=['北风','高塔'],mode='any'),{'1','2'})
        self.assertEqual(self.ids(keywords=['太阳','月'],mode='any'),{'3','4'})
        self.assertEqual(self.ids(keywords=['高塔','不存在'],mode='any'),{'1','2'})
        self.assertEqual(core.search(keywords=['北风','北风','高塔'],mode='any')['total'],2)
    def test_many_keywords_without_sql_variable_or_query_length_caps(self):
        terms=['不会命中'+str(i) for i in range(1200)]+['太阳']
        self.assertEqual(self.ids(keywords=terms,mode='any'),{'3'})
        status,data=dispatch('POST','/api/search',json.dumps({'keywords':terms,'mode':'any'}).encode())
        self.assertEqual(status,200);self.assertEqual(data['total'],1)
    def test_supplement_is_complete_and_idempotent(self):
        before=core.stats()['entries'];android_runtime.install_supplement()
        self.assertEqual(core.stats()['entries'],before+22)
        first=json.loads((core.ROOT/'research/moon-cards.json').read_text())[0]
        core.set_read(str(first['id']),True)
        android_runtime.install_supplement()
        self.assertEqual(core.stats()['entries'],before+22)
        self.assertTrue(core.is_read(str(first['id'])))
        manifest=catalog.parse_manifest(json.loads((core.ROOT/'research/catalog-249.json').read_text())['data'],'moon_cards')
        self.assertEqual(len(manifest['items']),22)
        for page in json.loads((core.ROOT/'research/moon-cards.json').read_text()):
            entry=core.get_entry(str(page['id']))
            self.assertEqual(entry['category'],'月谕圣牌');self.assertFalse(entry['warnings'])
            component=json.loads(page['modules'][0]['components'][0]['data'])
            from text_extract import plain
            expected=[plain(cell) for table in component['tables'] for row in [table.get('header',[])]+table.get('row',[]) for cell in row if plain(cell)]
            self.assertEqual([s['text'] for s in entry['sections']],expected)
