import json
import unittest
from pathlib import Path
import catalog
from text_extract import dialogue_blocks, extract_page, plain

ROOT = Path(__file__).parent / 'research'

class MapTextTests(unittest.TestCase):
    def test_manifest(self):
        data = json.loads((ROOT / 'catalog-251.json').read_text())
        self.assertEqual(len(catalog.parse_manifest(data, 'map_texts')['items']), 706)

    def test_real_pages_include_every_dialogue(self):
        for id in ['509612','509614','509613','508996','505726','503116','501971','968']:
            page = json.loads((ROOT / f'entry-{id}.json').read_text())['data']['page']
            entry = extract_page(page)
            self.assertFalse(entry['warnings'], id)
            expected = []
            for module in page['modules']:
                for component in module['components']:
                    if component['component_id'] == 'interactive_dialogue':
                        data = json.loads(component['data'])
                        for tree in data.get('list') or [data]:
                            for node in tree['contents'].values():
                                expected.extend(plain(node[k]) for k in ('option','dialogue') if plain(node.get(k)))
            actual = [s['text'] for s in entry['sections'] if s['text_type'] == '交互文本']
            self.assertCountEqual(expected, actual, id)
            self.assertTrue(actual)
            self.assertTrue(all('相关任务' not in s['title'] for s in entry['sections']))

    def test_virtual_root(self):
        tree = {'root_id':'r', 'contents':{'a':{'dialogue':'正文'}}, 'child_ids':{'r':['a'],'a':[]}}
        self.assertEqual([b[1] for b in dialogue_blocks(tree)], ['正文'])

    def test_branch_order_and_source_fields(self):
        tree = {'root_id':'r', 'contents':{'b':{'option':'乙','dialogue':'乙文'},'a':{'option':'甲','dialogue':'甲文'},'r':{'dialogue':'起点'}},'child_ids':{'r':['a','b']}}
        blocks = dialogue_blocks(tree)
        self.assertEqual([plain(b[1]) for b in blocks], ['起点','甲','甲文','乙','乙文'])
        self.assertIn('甲',blocks[2][0]);self.assertIn('.dialogue',blocks[2][2])
        tree['child_ids']['a']=['r']
        with self.assertRaises(ValueError): dialogue_blocks(tree)
        tree['child_ids']['a']=['missing']
        with self.assertRaises(ValueError): dialogue_blocks(tree)
        tree['child_ids']={'r':['a']}
        with self.assertRaises(ValueError): dialogue_blocks(tree)

if __name__ == '__main__': unittest.main()
