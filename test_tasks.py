import copy
import gzip
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import catalog
import import_jobs
import corpus_upgrade
from task_text import graph_nodes, metadata, task_sort_key

ROOT=Path(__file__).parent

def sample(id='399'):
    return json.loads((ROOT/f'research/tasks/entry-{id}.json').read_text())

class TaskTests(unittest.TestCase):
    def test_five_types_and_exclusive_manifests(self):
        source=json.loads((ROOT/'research/tasks/catalog.json').read_text());seen=set()
        for kind in ('archon','world','story','hangout','event'):
            m=catalog.parse_manifest(source,kind)
            ids={i['id'] for i in m['items']}
            self.assertTrue(ids);self.assertFalse(seen & ids);seen |= ids
        self.assertIn('1727',seen)
        self.assertEqual(metadata('「八重堂」的邀约',{})['kind'],'')
        self.assertEqual(len(seen),1109)

    def test_shared_graph_node_emitted_once_and_edges_preserved(self):
        tree={'root_id':'root','contents':{'a':{'option':'甲'},'b':{'option':'乙'},'c':{'dialogue':'共同后续'}},'child_ids':{'root':['a','b'],'a':['c'],'b':['c'],'c':[]}}
        result=graph_nodes(tree)
        self.assertEqual([r[0] for r in result],['root','a','b','c'])
        tree['child_ids']['c']=['a']
        with self.assertRaisesRegex(ValueError,'循环'):graph_nodes(tree)
        tree['child_ids']['c']=['missing']
        with self.assertRaisesRegex(ValueError,'缺失'):graph_nodes(tree)

    def test_real_samples_have_safe_stable_unique_sections_and_links(self):
        for id in ('399','398','652','509534','507289'):
            page=sample(id);entry=core.normalize(page)
            self.assertFalse(entry['incomplete'],id)
            ids=[s['id'] for s in entry['sections']]
            self.assertEqual(len(ids),len(set(ids)))
            self.assertTrue(all(link['id'] in ids for s in entry['sections'] for link in s['links']))
            page['modules'].reverse()
            self.assertEqual(ids,[s['id'] for s in core.normalize(page)['sections']])
            self.assertTrue(all('<script' not in s['html'] for s in entry['sections']))

    def test_missing_source_is_visible_not_claimed_as_full_dialogue(self):
        for id in ('1727','501056','6270'):
            entry=core.normalize(sample(id));self.assertTrue(entry['incomplete'])
            self.assertTrue(any(s['text_type']=='结局短句' for s in entry['sections']))
            self.assertFalse(any('攻略推荐' in s['text'] for s in entry['sections']))
        self.assertTrue(core.normalize(sample('510406'))['missing'])

    def test_escaped_angle_text_is_not_parsed_twice_or_dropped(self):
        page={'id':'900','name':'测试任务','menus':[{'id':'43','name':'任务'}],
              'modules':[{'id':'1','name':'剧情对话','components':[{'component_id':'interactive_dialogue','data':{'root_id':'root','child_ids':{'root':['a'],'a':[]},'contents':{'a':{'option':'&lt;省略&gt;'}}}}]}]}
        entry=core.normalize(page)
        self.assertEqual(entry['sections'][1]['text'],'<省略>')
        self.assertIn('&lt;省略&gt;',entry['sections'][1]['html'])
        self.assertEqual(entry['sections'][0]['links'][0]['id'],entry['sections'][1]['id'])

    def test_explicit_chapter_order(self):
        titles=['第十章 第一幕','第二章 第一幕','序章 第一幕','第一章 第二幕','第一章 第一幕']
        self.assertEqual(sorted(titles,key=task_sort_key),[titles[2],titles[4],titles[3],titles[1],titles[0]])

class TaskDBTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(core,'DB',Path(self.temp.name)/'db.sqlite3');self.patch.start()
        core.init_db();import_jobs.init_jobs()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_search_filter_partial_and_rewrite_retains_reading(self):
        a=core.normalize(sample());b=core.normalize(sample('1727'))
        core.save_entry(a);core.save_entry(b);core.set_read(a['id'],True);core.save_entry(a)
        self.assertTrue(core.get_entry(a['id'])['is_read'])
        self.assertEqual(core.search(category='邀约任务')['items'][0]['incomplete'],True)
        self.assertEqual(core.search(category='魔神任务',task_group=a['task']['group'])['total'],1)
        with core.connect() as db:
            self.assertIn('grams_entry',str([tuple(r) for r in db.execute('EXPLAIN QUERY PLAN DELETE FROM grams WHERE entry_id=?',('1',))]))
    def test_bundle_merge_keeps_newer_and_unknown_local_and_is_restartable(self):
        a=core.normalize(sample());a['version']='1700000000';core.save_entry(a);core.set_read(a['id'],True)
        b=copy.deepcopy(a);b['version']='1800000000';b['title']='更新后的标题'
        path=Path(self.temp.name)/'tasks.obc'
        with gzip.open(path,'wt') as out:out.write(json.dumps({'type':'entry','entry':b})+'\n')
        self.assertEqual(corpus_upgrade.install(path)['installed'],1)
        self.assertTrue(core.get_entry(a['id'])['is_read'])
        self.assertTrue(corpus_upgrade.install(path)['already_installed'])
        self.assertFalse(corpus_upgrade.should_replace(b,a))
        self.assertFalse(corpus_upgrade.should_replace({**a,'version':'unknown'},b))
        self.assertFalse(corpus_upgrade.should_replace(a,{**b,'incomplete':True}))
    def test_legacy_task_migration_does_not_reparse_existing_books(self):
        import sample_corpus
        from rebuild_text_cache import rebuild
        page=sample();old=core.normalize(page);old.pop('task');old.pop('task_parser_version');old['category']='任务'
        core.save_entry(old,raw_page=page)
        book_page=sample_corpus.raw_sample('503')[0];book=core.normalize(book_page);core.save_entry(book,raw_page=book_page)
        with patch.object(core,'normalize',wraps=core.normalize) as parse:
            result=rebuild();self.assertEqual(parse.call_count,1)
        self.assertEqual(result['updated'],['399'])
        self.assertEqual(core.get_entry('399')['category'],'魔神任务')
        self.assertEqual(core.get_entry('503')['fetched_at'],book['fetched_at'])

    def test_equal_revision_reparse_requires_identical_source(self):
        page=sample();incoming=core.normalize(page);old=copy.deepcopy(incoming)
        old.pop('task_parser_version');old.pop('task');old['category']='任务'
        core.save_entry(old,raw_page=page)
        path=Path(self.temp.name)/'same.obc'
        with gzip.open(path,'wt') as out:out.write(json.dumps({'type':'entry','entry':incoming,'source':page})+'\n')
        self.assertEqual(corpus_upgrade.install(path)['installed'],1)
        self.assertEqual(core.get_entry(old['id'])['category'],'魔神任务')
        self.assertEqual(core.get_entry(old['id'])['task_parser_version'],1)

    def test_interrupted_bundle_merge_resumes_without_losing_saved_entries(self):
        entries=[core.normalize(sample(id)) for id in ('399','652')]
        path=Path(self.temp.name)/'interrupted.obc'
        with gzip.open(path,'wt') as out:
            for entry in entries:out.write(json.dumps({'type':'entry','entry':entry})+'\n')
        real=core.save_entry
        def save(entry,**kwargs):
            if entry['id']=='652':raise OSError('simulated interruption')
            return real(entry,**kwargs)
        with patch.object(core,'save_entry',side_effect=save):
            with self.assertRaises(OSError):corpus_upgrade.install(path)
        self.assertIsNotNone(core.get_entry('399'))
        self.assertIsNone(core.get_entry('652'))
        result=corpus_upgrade.install(path)
        self.assertEqual(result['installed'],1);self.assertEqual(result['kept'],1)
        self.assertTrue(corpus_upgrade.install(path)['already_installed'])

    def test_parallel_downloads_pause_and_resume_without_duplicate_items(self):
        worker=import_jobs.Worker(concurrency=2);job=import_jobs.create_jobs(['books'])[0]
        m={'category':'books','items':[{'id':str(i),'title':str(i)} for i in (1,2,3)],'digest':'x'}
        import_jobs.install_manifest(job,m)
        barrier=threading.Barrier(2);calls=[]
        def fetch(id):
            calls.append(id);barrier.wait(timeout=3)
            import_jobs.action(job,'pause')
            return 'success',{}
        with patch.object(import_jobs,'fetch_and_check',side_effect=fetch):worker.run_job(job)
        self.assertEqual(import_jobs.job_details(job)['state'],'paused')
        self.assertEqual(set(calls),{'1','2'})
        import_jobs.action(job,'resume')
        with patch.object(import_jobs,'fetch_and_check',return_value=('success',{})) as f:
            worker.run_job(job);self.assertEqual(f.call_count,1)
        self.assertEqual(import_jobs.job_details(job)['done'],3)
    def test_entry_and_index_roll_back_together(self):
        entry=core.normalize(sample());core.save_entry(entry)
        bad=copy.deepcopy(entry);bad['title']='不能留下';bad['sections'].append(bad['sections'][0])
        with self.assertRaises(Exception):core.save_entry(bad)
        self.assertEqual(core.get_entry(entry['id'])['title'],entry['title'])

if __name__=='__main__':unittest.main()
