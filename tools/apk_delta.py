"""Transfer a verified APK using unchanged ZIP byte ranges from an earlier APK."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def data_offset(raw, info):
    name, extra = struct.unpack_from('<HH', raw, info.header_offset + 26)
    return info.header_offset + 30 + name + extra


def create(base, target, output):
    old, new = Path(base).read_bytes(), Path(target).read_bytes()
    ops = []
    def literal(data):
        if data: ops.append({'data': base64.b64encode(data).decode()})
    with zipfile.ZipFile(base) as a, zipfile.ZipFile(target) as b:
        index = {i.filename:i for i in a.infolist()}
        cursor = 0
        for info in sorted(b.infolist(), key=lambda i:i.header_offset):
            start = data_offset(new, info)
            literal(new[cursor:start])
            end = start + info.compress_size
            prior = index.get(info.filename)
            if prior is None:
                literal(new[start:end])
            else:
                old_start = data_offset(old, prior)
                x = old[old_start:old_start+prior.compress_size]
                y = new[start:end]
                prefix = 0
                limit = min(len(x),len(y))
                while prefix+65536 <= limit and x[prefix:prefix+65536] == y[prefix:prefix+65536]: prefix += 65536
                while prefix < limit and x[prefix] == y[prefix]: prefix += 1
                suffix = 0
                while suffix+65536 <= limit-prefix and x[len(x)-suffix-65536:len(x)-suffix] == y[len(y)-suffix-65536:len(y)-suffix]: suffix += 65536
                while suffix < limit-prefix and x[-suffix-1] == y[-suffix-1]: suffix += 1
                if prefix: ops.append({'copy':[old_start,prefix]})
                literal(y[prefix:len(y)-suffix if suffix else len(y)])
                if suffix: ops.append({'copy':[old_start+len(x)-suffix,suffix]})
            cursor = end
        literal(new[cursor:])
    patch = {'base_sha256':sha(old),'sha256':sha(new),'bytes':len(new),'ops':ops}
    with gzip.open(output,'wt') as f: json.dump(patch,f,separators=(',',':'))
    print(json.dumps({k:patch[k] for k in ('base_sha256','sha256','bytes')}))


def apply(base, patch, output):
    old = Path(base).read_bytes()
    with gzip.open(patch,'rt') as f: spec=json.load(f)
    assert sha(old)==spec['base_sha256'], 'Wrong base APK'
    result=bytearray()
    for op in spec['ops']:
        if 'copy' in op:
            start,size=op['copy'];assert start>=0 and size>=0 and start+size<=len(old)
            result.extend(old[start:start+size])
        else: result.extend(base64.b64decode(op['data'],validate=True))
    assert len(result)==spec['bytes'] and sha(result)==spec['sha256'], 'APK checksum mismatch'
    Path(output).write_bytes(result)
    print('Verified APK',len(result),sha(result))


if __name__=='__main__':
    {'create':create,'apply':apply}[sys.argv[1]](*sys.argv[2:])
