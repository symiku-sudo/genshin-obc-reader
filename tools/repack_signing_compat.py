"""Repack only build metadata; application files must remain byte-identical."""
import argparse
import hashlib
import zipfile

UNSIGNED_METADATA = {
    'META-INF/com/android/build/gradle/app-metadata.properties',
    'META-INF/version-control-info.textproto',
    'META-INF/androidx.annotation_annotation-experimental.version',
    'META-INF/androidx.core_core.version',
    'META-INF/androidx.lifecycle_lifecycle-runtime.version',
    'META-INF/androidx.versionedparcelable_versionedparcelable.version',
    'META-INF/androidx.webkit_webkit.version',
}

def signature(name):
    return name.startswith('META-INF/') and (name.endswith(('.RSA', '.SF', '.DSA', '.EC')) or name == 'META-INF/MANIFEST.MF')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('original')
    parser.add_argument('output')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    with zipfile.ZipFile(args.original) as source:
        names = {n for n in source.namelist() if not signature(n) and n not in UNSIGNED_METADATA}
        if args.verify:
            with zipfile.ZipFile(args.output) as target:
                assert {n for n in target.namelist() if not signature(n)} == names
                for name in names:
                    assert hashlib.sha256(source.read(name)).digest() == hashlib.sha256(target.read(name)).digest(), name
                assert target.testzip() is None
            print('Application payload unchanged:', len(names), 'entries')
        else:
            with zipfile.ZipFile(args.output, 'w') as target:
                for info in source.infolist():
                    if info.filename in names:
                        target.writestr(info, source.read(info.filename))
            print('Removed unsigned metadata:', sorted(set(source.namelist()) & UNSIGNED_METADATA))

if __name__ == '__main__':
    main()
