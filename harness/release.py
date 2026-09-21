"""Detect drift in an installed release; this is integrity checking, not signing."""
from pathlib import Path
import json
import re
from .common import encoded, sha256, safe_relative, fail


def verify_release(root=None):
    from .history import _no_links
    root=Path(root or Path(__file__).resolve().parents[1])
    manifest_path=root/'release-manifest.json'
    _no_links(root); _no_links(manifest_path)
    if not manifest_path.is_file():
        if root.parent.name=='releases': fail('release_manifest_missing','Installed runtime release has no integrity manifest.')
        return {'release_id':'working-source','verified':False}
    try:
        if manifest_path.stat().st_size>4*1024*1024: fail('invalid_release','Release manifest exceeds 4 MiB.')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    except (ValueError,OSError):
        fail('invalid_release','Release manifest is unreadable or invalid JSON.')
    if not isinstance(manifest,dict) or not all(isinstance(manifest.get(key),str) for key in ['version','release_id','content_sha256']):
        fail('invalid_release','Release identity fields must be strings in an object.')
    files=manifest.get('files',[])
    if not isinstance(files,list) or not files or len(files)>10000: fail('invalid_release','Invalid release file inventory.')
    digest=sha256(encoded(files))
    if digest!=manifest.get('content_sha256') or manifest.get('release_id')!=manifest.get('version','')+'-'+digest[:16]:
        fail('release_modified','Runtime release manifest identity is inconsistent.')
    seen=set()
    for row in files:
        if not isinstance(row,dict) or not isinstance(row.get('path'),str) or not isinstance(row.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']):
            fail('invalid_release','Release rows require a relative path and SHA-256 digest.')
        relative=str(safe_relative(row['path']))
        if relative in seen: fail('invalid_release','Duplicate release path.')
        seen.add(relative)
        path=root/relative; _no_links(path)
        if not path.is_file() or sha256(path.read_bytes())!=row['sha256']:
            fail('release_modified','Runtime release file changed: '+relative)
    for path in root.rglob('*.py'):
        _no_links(path)
        if path.relative_to(root).as_posix() not in seen:
            fail('release_modified','An unlisted Python module was added to the runtime release.')
    return {'release_id':manifest['release_id'],'verified':True,'file_count':len(files)}
