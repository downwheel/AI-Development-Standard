"""Refresh reviewed deployment hashes. Does not install or change the package version."""
import json
from package_lib import ROOT, inventory, load_package

def main():
    path = ROOT / 'manifest.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    files = inventory()
    data['package_files'] = [{'path': p, 'sha256': h} for p, h in sorted(files.items())]
    data['files'] = [row for row in data['package_files'] if row['path'].startswith('skills/codex/')]
    data['claude_files'] = [row for row in data['package_files'] if row['path'].startswith('skills/claude/')]
    original = path.read_bytes()
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        load_package()
    except Exception:
        path.write_bytes(original)
        raise
    print(json.dumps({'version': data['version'], 'skill_files': len(data['files']),
                      'package_files': len(data['package_files']), 'installed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
