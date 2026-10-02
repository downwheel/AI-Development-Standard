"""Build a verified portable ZIP outside the repository, without private files or Git metadata."""
from pathlib import Path
import argparse
import json
import zipfile
from package_lib import ROOT, load_package, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='Absolute ZIP path outside the repository')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if not args.output.expanduser().is_absolute() or output == ROOT or ROOT in output.parents:
        parser.error('Use an absolute output path outside the repository')
    if output.suffix.lower() != '.zip':
        parser.error('Output must end with .zip')
    data = load_package()
    prefix = 'AI-Development-Standard/'
    entries = {row['path']: (ROOT / row['path']).read_bytes() for row in data['package_files']}
    entries['manifest.json'] = (ROOT / 'manifest.json').read_bytes()
    for row in data['package_files']:
        if sha(entries[row['path']]) != row['sha256']:
            raise ValueError('Package changed while reading: ' + row['path'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for rel, content in sorted(entries.items()):
            info = zipfile.ZipInfo(prefix + rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    with zipfile.ZipFile(output) as archive:
        for rel, content in entries.items():
            if archive.read(prefix + rel) != content:
                raise RuntimeError('ZIP verification failed: ' + rel)
    print(json.dumps({'version': data['version'], 'archive': str(output), 'files': len(entries),
                      'sha256': sha(output.read_bytes())}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
