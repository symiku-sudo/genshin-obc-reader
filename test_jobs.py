import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import catalog
import import_jobs as jobs
import sample_corpus

class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(core,'DB',Path(self.tmp.name)/'db.sqlite3');self.db.start()
        core.init_db();jobs.init_jobs();self.worker=jobs.Worker()
        self.manifest={'category':'books','name':'书籍','channel_id':'68','fetched_at':catalog.now(),'raw_count':2,'duplicates':0,'items':[{'id':'503','title':'书籍A'},{'id':'625','title':'书籍B'}],'digest':'test','scope':'test'}
    def tearDown(self): self.db.stop();self.tmp.cleanup()
    def raw(self,id): return sample_corpus.raw_sample(id)[0]
    def runjob(self,id):
        with patch.object(catalog,'fetch_manifest',return_value=self.manifest),patch.object(core,'upstream',side_effect=lambda path,params,**kw:{'page':self.raw(params['entry_page_id'])}): self.worker.run_job(id)
    def test_import_idempotency_and_incremental_unchanged(self):
        id=jobs.create_jobs(['books'])[0]
        self.assertEqual(jobs.create_jobs(['books'])[0],id)
        self.runjob(id);self.assertEqual(jobs.job_details(id)['counts']['success'],2)
        old=core.get_entry('503')['fetched_at']
        nextid=jobs.create_jobs(['books'])[0];self.assertNotEqual(id,nextid)
        with patch.object(core,'save_entry',wraps=core.save_entry) as save:
            self.runjob(nextid);save.assert_not_called()
        self.assertEqual(jobs.job_details(nextid)['counts']['unchanged'],2)
        self.assertEqual(core.get_entry('503')['fetched_at'],old)
    def test_pause_resume_preserves_completed_items(self):
        id=jobs.create_jobs(['books'])[0];jobs.action(id,'pause')
        self.runjob(id);self.assertEqual(jobs.job_details(id)['state'],'paused')
        jobs.action(id,'resume')
        original=jobs.fetch_and_check
        def fetch(entry):
            result=original(entry);jobs.action(id,'pause');return result
        with patch.object(jobs,'fetch_and_check',side_effect=fetch): self.runjob(id)
        d=jobs.job_details(id);self.assertEqual(d['state'],'paused');self.assertEqual(d['done'],1)
        jobs.action(id,'resume');self.runjob(id)
        d=jobs.job_details(id);self.assertEqual(d['done'],2);self.assertEqual(d['state'],'completed')
        self.assertTrue(all(x['attempts']==1 for x in d['items']))
    def test_process_restart_recovers_inflight_to_paused_pending(self):
        id=jobs.create_jobs(['books'])[0];jobs.install_manifest(id,self.manifest)
        with core.connect() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?",(id,));db.execute("UPDATE job_items SET state='processing' WHERE job_id=?",(id,))
        jobs.init_jobs(recover=True)
        self.assertEqual(jobs.job_details(id)['state'],'paused');self.assertEqual(jobs.job_details(id)['counts']['pending'],2)
        jobs.action(id,'resume');self.runjob(id);self.assertEqual(jobs.job_details(id)['done'],2)
    def test_failure_retry_only_failed_items_and_old_cache_survives(self):
        old=core.normalize(self.raw('503'));core.save_entry(old)
        id=jobs.create_jobs(['books'])[0]
        with patch.object(catalog,'fetch_manifest',return_value=self.manifest),patch.object(jobs,'fetch_and_check',side_effect=[ValueError('bad response'),('no_text',{})]): self.worker.run_job(id)
        self.assertEqual(core.get_entry('503')['fetched_at'],old['fetched_at'])
        self.assertEqual(jobs.job_details(id)['counts']['failed'],1)
        jobs.action(id,'retry')
        with patch.object(jobs,'fetch_and_check',return_value=('success',{})) as fetch:self.worker.run_job(id)
        self.assertEqual(fetch.call_count,1);self.assertEqual(jobs.job_details(id)['counts']['failed'],0)
    def test_three_transient_attempts_are_bounded(self):
        self.manifest['items']=self.manifest['items'][:1]
        id=jobs.create_jobs(['books'])[0]
        with patch.object(catalog,'fetch_manifest',return_value=self.manifest),patch.object(jobs,'fetch_and_check',side_effect=OSError('offline')) as fetch,patch.object(self.worker.stop_event,'wait',return_value=False):self.worker.run_job(id)
        self.assertEqual(fetch.call_count,3);self.assertEqual(jobs.job_details(id)['counts']['failed'],1)
    def test_no_text_is_distinct_from_unadapted(self):
        empty={'id':'9','name':'empty','version':'1','modules':[]}
        unknown={**empty,'modules':[{'id':'1','components':[{'component_id':'new_widget','data':'{"story":"text"}'}]}]}
        with patch.object(core,'upstream',return_value={'page':empty}):self.assertEqual(jobs.fetch_and_check('9')[0],'no_text')
        with patch.object(core,'upstream',return_value={'page':unknown}):self.assertEqual(jobs.fetch_and_check('9')[0],'review')
    def test_failed_catalog_does_not_replace_previous_snapshot(self):
        id=jobs.create_jobs(['books'])[0];self.runjob(id)
        nextid=jobs.create_jobs(['books'])[0]
        with patch.object(catalog,'fetch_manifest',side_effect=ValueError('truncated')):self.worker.run_job(nextid)
        self.assertEqual(jobs.job_details(nextid)['state'],'failed')
        self.assertEqual(jobs.dashboard()['categories'][0]['total'],2)
    def test_removed_directory_items_keep_offline_text(self):
        id=jobs.create_jobs(['books'])[0];self.runjob(id)
        self.manifest['items']=self.manifest['items'][:1]
        self.runjob(jobs.create_jobs(['books'])[0])
        self.assertEqual(jobs.dashboard()['categories'][0]['unlisted'],1)
        self.assertIsNotNone(core.get_entry('625'))

class CatalogTests(unittest.TestCase):
    def data(self):return json.loads((core.ROOT/'research/catalog-68.json').read_text())['data']
    def test_actual_catalog_counts(self):
        for c,n,id in [('books',93,'68'),('weapons',252,'5'),('artifacts',63,'218')]:
            d=json.loads((core.ROOT/f'research/catalog-{id}.json').read_text())['data']
            m=catalog.parse_manifest(d,c);self.assertEqual(len(m['items']),n);self.assertEqual(m['duplicates'],0)
    def test_duplicate_ids_deduplicated_and_conflicts_rejected(self):
        d=self.data();d['list'][0]['list'].append(copy.deepcopy(d['list'][0]['list'][0]))
        self.assertEqual(catalog.parse_manifest(d,'books')['duplicates'],1)
        d['list'][0]['list'][-1]['title']='conflict'
        with self.assertRaises(ValueError):catalog.parse_manifest(d,'books')
    def test_truncated_empty_wrong_category_and_nested_lists_rejected(self):
        for change in [{'entry_limit':10},{'children':[{'id':1}]},{'list':[]},{'id':5}]:
            d=self.data();d['list'][0].update(change)
            with self.assertRaises(ValueError):catalog.parse_manifest(d,'books')

if __name__=='__main__':unittest.main()
