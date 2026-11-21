"""Publish a pinned, successful build from an explicit release/<version> push."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    config = json.loads(Path('release.json').read_text())
    version = config['version']
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    assert os.environ['RELEASE_BRANCH'] == 'release/' + version
    repo = os.environ['REPO']

    def api(path, method='GET', data=None):
        args = ['gh', 'api', 'repos/' + repo + '/' + path, '--method', method]
        if data is not None:
            args += ['--input', '-']
        raw = subprocess.check_output(args, input=json.dumps(data).encode() if data is not None else None)
        return json.loads(raw) if raw else None

    run_id = config['run_id']
    run = api(f'actions/runs/{run_id}')
    assert run['conclusion'] == 'success'
    assert run['head_sha'] == config['source_commit']
    assert run['head_repository']['full_name'] == repo
    artifacts = api(f'actions/runs/{run_id}/artifacts')['artifacts']
    artifact = next(a for a in artifacts if a['name'] == 'obc-reader-release')
    assert artifact['digest'] == config['artifact_digest'] and not artifact['expired']
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        subprocess.run(['gh', 'run', 'download', str(run_id), '--repo', repo,
                        '--name', 'obc-reader-release', '--dir', str(root)], check=True)
        apk = root / 'app-release.apk'
        digest = hashlib.sha256(apk.read_bytes()).hexdigest()
        assert digest == (root / 'app-release.apk.sha256').read_text().split()[0]
        signature = (root / 'signing-verification.txt').read_text()
        assert '2d59993be66a227aff2ccb8f5beb094b5766b54d9cc3edf8ad3e65fccaa310a3' in signature
        for scheme in ['v1 scheme (JAR signing)', 'v2 scheme (APK Signature Scheme v2)', 'v3 scheme (APK Signature Scheme v3)']:
            assert 'Verified using ' + scheme + ': true' in signature
        subprocess.run(['python', 'tools/verify_android_apk.py', str(apk)], check=True)
        apk = apk.rename(root / f'obc-reader-{version}.apk')
        checksum = root / (apk.name + '.sha256')
        checksum.write_text(digest + '  ' + apk.name + '\n')
        provenance = root / 'provenance.json'
        provenance.write_text(json.dumps({'source_commit': run['head_sha'], 'run_id': run_id,
                                         'run_url': run['html_url'], 'sha256': digest,
                                         'bytes': apk.stat().st_size}, indent=2) + '\n')
        tag = 'v' + version
        release = next((r for r in api('releases?per_page=100') if r['tag_name'] == tag), None)
        if release is None:
            release = api('releases', 'POST', {'tag_name': tag, 'target_commitish': run['head_sha'],
                          'name': '观测观测枢 ' + version, 'draft': True,
                          'body': Path(f'docs/releases/{version}.md').read_text()})
        paths = [apk, checksum, root / 'signing-verification.txt', provenance]
        # Published assets can only be replaced with an explicitly pinned prior APK.
        replace_digest = config.get('replace_asset_sha256')
        if replace_digest and not release['draft']:
            assert re.fullmatch(r'[0-9a-f]{64}', replace_digest)
            existing = next(a for a in release['assets'] if a['name'] == apk.name)
            assert existing['digest'] in {'sha256:' + replace_digest, 'sha256:' + digest}
        if release['draft'] or replace_digest:
            subprocess.run(['gh', 'release', 'upload', tag, '--repo', repo, '--clobber',
                            *map(str, paths)], check=True)
        release = api('releases/' + str(release['id']))
        for path in paths:
            asset = next(a for a in release['assets'] if a['name'] == path.name)
            assert asset['state'] == 'uploaded' and asset['size'] == path.stat().st_size
            assert asset['digest'] == 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
            print('Verified asset:', path.name, asset['size'], asset['digest'], flush=True)
        if release['draft']:
            release = api('releases/' + str(release['id']), 'PATCH', {'draft': False, 'prerelease': bool(config.get('prerelease', False)), 'make_latest': 'false' if config.get('prerelease') else 'true'})
        elif replace_digest:
            release = api('releases/' + str(release['id']), 'PATCH', {
                'body': Path(f'docs/releases/{version}.md').read_text(),
                'prerelease': bool(config.get('prerelease', False)),
                'make_latest': 'false' if config.get('prerelease') else 'true'})
        print('Published:', release['html_url'], flush=True)


if __name__ == '__main__':
    main()
