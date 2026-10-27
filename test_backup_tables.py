import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
from text_extract import extract_page, extract_tables, plain

class BackupTableTests(unittest.TestCase):
    def test_explicit_prose_columns(self):
        page=json.loads((Path(__file__).parent/'research/entry-4516.json').read_text())['data']['page']
        entry=extract_page(page)
        expected=[]
        for module in page['modules']:
            for component in module['components']:
                if component['component_id']=='multi_table':
                    for table in json.loads(component['data'])['tables']:
                        if table['header'][-1]=='文案': expected.extend(plain(row[2]) for row in table['row'])
        actual=[s['text'] for s in entry['sections'] if s['text_type']=='正文']
        self.assertEqual(expected,actual)
        self.assertEqual(len(actual),13)
        self.assertFalse(entry['warnings'])

    def test_unknown_tables_are_not_silently_discarded(self):
        blocks,unknown=extract_tables({'tables':[{'header':['故事','插图','文案'],'row':[['题','','正文']]},{'header':['描述'],'row':[['未知正文']]}]})
        self.assertEqual(len(blocks),1);self.assertTrue(unknown)
        self.assertEqual(extract_tables({'tables':[{'header':['详细属性','数量'],'row':[['材料','3']]}]}),([],False))

    def test_backup_merge_and_validation_are_nondestructive(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(core,'DB',Path(tmp)/'db'):
            core.init_db()
            core.merge_reading(['1','2','2'])
            core.merge_reading(['2','3'])
            self.assertEqual(core.reading_backup()['read_entries'],['1','2','3'])
            for invalid in [['4','bad'], '1', [1], None]:
                with self.assertRaises(ValueError):core.merge_reading(invalid)
            self.assertEqual(core.reading_backup()['read_entries'],['1','2','3'])
            core.init_db()
            self.assertTrue(core.is_read('3'))

if __name__=='__main__':unittest.main()
