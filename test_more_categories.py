import json
import unittest
from pathlib import Path
from collections import Counter
import catalog
from text_extract import extract_page, plain

ROOT = Path(__file__).parent / 'research'

class MoreCategoryTests(unittest.TestCase):
    def test_complete_manifests(self):
        for key, channel, total in [('characters','25',138),('food','21',323),('inventory','13',2052)]:
            data = json.loads((ROOT / f'catalog-{channel}.json').read_text())
            manifest = catalog.parse_manifest(data, key)
            self.assertEqual(len(manifest['items']), total)
            self.assertEqual(manifest['duplicates'], 0)

    def test_actual_page_prose_and_chinese_voice(self):
        for id in ['510137','5865','505499','510043','5961','80','510128','7102','499']:
            page = json.loads((ROOT / f'entry-{id}.json').read_text())['data']['page']
            entry = extract_page(page)
            self.assertTrue(entry['sections'], id)
            self.assertFalse(entry['warnings'], id)
            voice = []
            descriptions = []
            for module in page['modules']:
                if module.get('is_hidden'): continue
                for component in module['components']:
                    data = json.loads(component['data'])
                    if component['component_id'] == 'role_voice':
                        for tab in data.get('list', []):
                            if plain(tab.get('tab_name')) in ('汉语','中文','简体中文'):
                                voice.extend(plain(v['content']) for v in tab.get('table',[]) if plain(v.get('content')))
                    if component['component_id'] == 'material_base_info':
                        descriptions.extend(plain(a['value']) for a in data.get('attr',[]) if plain(a.get('key')).strip(' ：:') in ('描述','介绍','简介','故事','背景故事','作者') and plain(a.get('value')))
            actual = Counter(s['text'] for s in entry['sections'])
            self.assertFalse(set(voice)-set(actual), id)
            self.assertFalse(Counter(descriptions)-actual, id)
            voice_modules = {str(m['id']) for m in page['modules'] if any(c['component_id']=='role_voice' for c in m['components'])}
            extracted_voice = {s['text'] for s in entry['sections'] if s['module_id'] in voice_modules}
            self.assertEqual(extracted_voice, set(voice), id)

if __name__ == '__main__': unittest.main()
