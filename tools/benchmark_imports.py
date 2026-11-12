"""Reproducible offline scheduling benchmark; simulated latency is explicitly reported."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import tempfile
import time
from unittest.mock import patch
import core
import import_jobs


def main():
    source=json.loads((core.ROOT/'research/tasks/entry-652.json').read_text())
    results=[]
    for concurrency in (1,2):
        with tempfile.TemporaryDirectory() as directory, patch.object(core,'DB',Path(directory)/'library.sqlite3'):
            core.init_db();import_jobs.init_jobs();worker=import_jobs.Worker(concurrency=concurrency)
            manifest={'category':'world','items':[{'id':str(i),'title':'样本'} for i in range(100,112)],'digest':'benchmark'}
            def fetch(path, params, **kwargs):
                time.sleep(.15)
                return {'page':dict(source,id=params['entry_page_id'])}
            times={}
            for mode in ('first_import','unchanged_update'):
                job=import_jobs.create_jobs(['world'])[0];import_jobs.install_manifest(job,manifest)
                start=time.perf_counter()
                with patch.object(core,'upstream',side_effect=fetch):worker.run_job(job)
                times[mode]=round(time.perf_counter()-start,4)
                times[mode+'_counts']=import_jobs.job_details(job)['counts']
            results.append({'concurrency':concurrency,**times})
    print(json.dumps({'network':'simulated 150ms per request; not a real-network speed claim','entries':12,'results':results},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
