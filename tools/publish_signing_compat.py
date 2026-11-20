"""Publish verified compatibility packaging to the user-authorized existing URL."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path('repaired')
apk = root / 'obc-reader-1.3.1.apk'
digest = hashlib.sha256(apk.read_bytes()).hexdigest()
repo = os.environ['GITHUB_REPOSITORY']
run = os.environ['GITHUB_RUN_ID']
provenance = root / 'provenance.json'
provenance.write_text(json.dumps({
    'source_commit': 'f74ee30281802538382c12a4b420fc338c19c48e',
    'packaging_commit': os.environ['GITHUB_SHA'],
    'run_id': int(run), 'run_url': f'https://github.com/{repo}/actions/runs/{run}',
    'original_sha256': '54e6ac4d53b36d314b656a5bc9359c1a0f9a2e8496f855267c4cf15fef0fa948',
    'sha256': digest, 'bytes': apk.stat().st_size,
    'changes': 'Remove unsigned build metadata, align and re-sign with the unchanged developer certificate. Application payload is byte-identical.',
}, indent=2) + '\n')
files = [apk, root / (apk.name + '.sha256'), root / 'signing-verification.txt', provenance]
subprocess.run(['gh', 'release', 'upload', 'v1.3.1', '--clobber', *map(str, files)], check=True)
release = json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/releases/tags/v1.3.1']))
for path in files:
    asset = next(a for a in release['assets'] if a['name'] == path.name)
    assert asset['size'] == path.stat().st_size
    assert asset['digest'] == 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
note = '\n\n### 安装兼容性重签包\n\n已清理未参与 JAR 签名的构建元数据，并使用原开发者证书重新签名，v1/v2/v3 签名及 Android 覆盖安装验证通过。版本号、应用代码和文本库不变，下载地址不变。此调整用于排查部分 vivo 设备的证书提示，尚未在报告问题的 vivo 设备上确认解决。\n'
notes = root / 'release-notes.md'
notes.write_text(release['body'] + note)
subprocess.run(['gh', 'release', 'edit', 'v1.3.1', '--notes-file', str(notes)], check=True)
print('Updated existing release:', release['html_url'], 'SHA256:', digest)
