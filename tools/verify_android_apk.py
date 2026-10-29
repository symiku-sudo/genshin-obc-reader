#!/usr/bin/env python3
"""Verify the actual APK contains the complete, unmodified offline corpus."""
import argparse
import gzip
import hashlib
import json
import zipfile
from pathlib import Path


def verify(path):
    with zipfile.ZipFile(path) as apk:
        names = set(apk.namelist())
        for name in ('assets/web/index.html', 'assets/web/app.js', 'assets/web/runtime.js',
                     'assets/web/reading.js', 'assets/web/library.js', 'assets/web/backup.js', 'assets/web/catalog-channels.json',
                     'assets/resources/research/entry-1600.json', 'assets/corpus.json',
                     'assets/library.obc', 'classes.dex', 'AndroidManifest.xml'):
            if name not in names:
                raise ValueError('Missing offline component: ' + name)
        for abi in ('arm64-v8a', 'x86_64'):
            if not any(name.startswith('lib/' + abi + '/') and 'python' in name for name in names):
                raise ValueError('Missing embedded Python for ' + abi)
        manifest = json.loads(apk.read('assets/corpus.json'))
        digest = hashlib.sha256()
        size = 0
        with apk.open('assets/library.obc') as packed, gzip.GzipFile(fileobj=packed) as raw:
            while block := raw.read(1024 * 1024):
                size += len(block)
                digest.update(block)
        if size != manifest['bytes'] or digest.hexdigest() != manifest['sha256']:
            raise ValueError('Bundled corpus differs from verified snapshot')
        html = apk.read('assets/web/index.html').decode()
        if html.index('runtime.js') > html.index('app.js'):
            raise ValueError('Native bridge loads after the application')
        if 'Content-Security-Policy' not in html:
            raise ValueError('Bundled page is missing its content security policy')
    print(json.dumps({'apk': path.name, 'apk_bytes': path.stat().st_size,
                      'corpus_entries': manifest['entries'], 'corpus_sections': manifest['sections'],
                      'corpus_sha256': manifest['sha256'], 'verified': True}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    verify(parser.parse_args().apk)
