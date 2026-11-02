"""Android's in-process Python host. No listening socket or external service."""
import json
import threading
from pathlib import Path
import core
import import_jobs
from api_service import dispatch

_worker = None
_lock = threading.Lock()


def initialize(files_dir, resource_dir):
    global _worker
    with _lock:
        if _worker is not None:
            return
        core.ROOT = Path(resource_dir)
        core.DB = Path(files_dir) / 'library.sqlite3'
        core.init_db()
        from rebuild_text_cache import rebuild
        rebuild()
        install_supplement()
        import_jobs.init_jobs(recover=True)
        _worker = import_jobs.Worker()
        _worker.start()


def request(method, path, body=''):
    status, data = dispatch(method, path, body.encode('utf-8'), _worker)
    return json.dumps({'status': status, 'data': data}, ensure_ascii=False)


def install_supplement():
    """Merge new bundled cards on upgrades without overwriting a user's newer cache."""
    path = core.ROOT / 'research' / 'moon-cards.json'
    if not path.exists(): return
    for page in json.loads(path.read_text()):
        if core.get_entry(str(page['id'])) is None:
            core.save_entry(core.normalize(page), raw_page=page)
