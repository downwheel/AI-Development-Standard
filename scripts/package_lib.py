"""Shared package checks. Uses only Python's standard library and writes nothing."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {'.gitattributes', '.gitignore', 'AGENTS.md', 'CLAUDE.md', 'LICENSE', 'README.md', 'START-HERE.md', 'START-HERE-CODEX.md', 'START-HERE-CLAUDE.md'}
PACKAGE_DIRS = {'adapters', 'docs', 'scripts', 'skills', 'integrations'}
LEGACY_SKILLS = {'development-workflow', 'dev-artifacts', 'dev-discover', 'dev-environment',
                 'dev-implement', 'dev-requirements', 'dev-restore', 'dev-review',
                 'dev-system-design', 'dev-test-design', 'dev-unit-design', 'dev-verify', 'dev-slack'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def valid_name(name):
    return (isinstance(name, str) and 0 < len(name) <= 64
            and name == unicodedata.normalize('NFC', name)
            and not name.startswith('-') and not name.endswith('-') and '--' not in name
            and all(c == '-' or c.isdecimal() or (c.isalpha() and c == c.lower()) for c in name))


def no_links(path):
    for item in [path, *path.parents]:
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 1024):
            raise ValueError('Linked paths are not supported: ' + str(item))


def inventory(root=ROOT):
    """Only public deployment inputs may enter the package inventory."""
    files = {}
    for top in root.iterdir():
        if top.name == '.git' or top.name == 'manifest.json':
            continue
        if top.name not in TOP_FILES | PACKAGE_DIRS:
            raise ValueError('Unexpected distribution entry; keep artifacts outside the repository: ' + top.name)
        no_links(top)
        paths = top.rglob('*') if top.is_dir() else [top]
        for path in paths:
            no_links(path)
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if path.name.startswith('.env') or path.suffix.lower() in {'.pem', '.key', '.pfx', '.pyc'} or '__pycache__' in path.parts:
                raise ValueError('Private or generated file cannot be distributed: ' + rel)
            if path.name in {'config.toml', 'auth.json', 'team-skills.json', 'team-skills-receipt.json', 'team-tools-receipt.json', '.claude.json', 'runtime.json'}:
                raise ValueError('Machine-specific configuration cannot be distributed: ' + rel)
            files[rel] = sha(path.read_bytes())
    return files


def declared_files(rows):
    result = {}
    for row in rows:
        rel, digest = row['path'], row['sha256']
        parts = PurePosixPath(rel)
        if (not isinstance(rel, str) or '\\' in rel or ':' in rel or parts.is_absolute()
                or '..' in parts.parts or str(parts) != rel or rel in result
                or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('Invalid or duplicate manifest path/hash: ' + str(rel))
        result[rel] = digest
    return result


def load_package(root=ROOT):
    no_links(root / 'manifest.json')
    data = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    names = data['skill_names']
    if data.get('schema_version') != 3 or data.get('edition') != 'codex-and-claude':
        raise ValueError('Unsupported distribution manifest')
    if not re.fullmatch(r'\d+\.\d+\.\d+', data.get('version', '')):
        raise ValueError('A package version is required')
    if len(names) != 27 or len(set(names)) != 27 or any(not valid_name(n) for n in names):
        raise ValueError('Expected the reviewed 27-skill selection')
    actual = inventory(root)
    if actual != declared_files(data['package_files']):
        raise ValueError('Package manifest mismatch. Review changes, then run scripts/update_manifest.py.')
    skills = {p: h for p, h in actual.items() if p.startswith('skills/codex/')}
    if skills != declared_files(data['files']):
        raise ValueError('Skill file manifest mismatch')
    if {p.name for p in (root / 'skills/codex').iterdir()} != set(names):
        raise ValueError('Skill folders differ from the declared selection')
    implicit = 0
    for name in names:
        folder = root / 'skills/codex' / name
        entry = (folder / 'SKILL.md').read_text(encoding='utf-8')
        front = re.match(r'\A---\n(.*?)\n---(?:\n|$)', entry, re.S)
        if not front or not re.search(r'^name: ' + re.escape(name) + r'\s*$', front[1], re.M):
            raise ValueError('Skill name does not match its folder: ' + name)
        desc = re.search(r'^description: (.+)$', front[1], re.M)
        if not desc or not re.search('[가-힣]', desc[1]):
            raise ValueError('A Korean skill description is required: ' + name)
        meta = (folder / 'agents/openai.yaml').read_text(encoding='utf-8')
        display = re.search(r'^  display_name: (.+)$', meta, re.M)
        if not display or display[1].strip('"\'') != name:
            raise ValueError('Skill display name mismatch: ' + name)
        flag = re.search(r'^  allow_implicit_invocation: (true|false)$', meta, re.M)
        if not flag:
            raise ValueError('Missing skill invocation policy: ' + name)
        implicit += flag[1] == 'true'
        if (folder / 'LICENSE').read_bytes() != (root / 'LICENSE').read_bytes():
            raise ValueError('License notice missing or changed: ' + name)
    if implicit != 11:
        raise ValueError('Expected 11 implicit and 16 explicit skills')
    claude_files={p:h for p,h in actual.items() if p.startswith('skills/claude/')}
    if claude_files!=declared_files(data['claude_files']):
        raise ValueError('Claude skill manifest mismatch')
    if {p.name for p in (root/'skills/claude').iterdir()}!=set(names):
        raise ValueError('Claude skill folders differ from the declared selection')
    for name in names:
        folder=root/'skills/claude'/name
        entry=(folder/'SKILL.md').read_text(encoding='utf-8')
        front=re.match(r'\A---\n(.*?)\n---(?:\n|$)',entry,re.S)
        meta=(root/'skills/codex'/name/'agents/openai.yaml').read_text(encoding='utf-8')
        expected='false' if 'allow_implicit_invocation: true' in meta else 'true'
        if not front or not re.search(r'^name: '+re.escape(name)+r'\s*$',front[1],re.M) or 'disable-model-invocation: '+expected not in front[1]:
            raise ValueError('Claude name/invocation policy mismatch: '+name)
        if not re.search(r'^description: .*[가-힣]',front[1],re.M) or (folder/'agents/openai.yaml').exists():
            raise ValueError('Invalid Claude metadata: '+name)
        if (folder/'LICENSE').read_bytes()!=(root/'LICENSE').read_bytes():
            raise ValueError('Claude license mismatch: '+name)
    return data


def legacy_findings(home,edition='codex'):
    findings = []
    for name in sorted(LEGACY_SKILLS):
        if (home / 'skills' / name).exists():
            findings.append('skills/' + name)
    agents = home / ('AGENTS.md' if edition=='codex' else 'CLAUDE.md')
    if agents.is_file():
        content = agents.read_text(encoding='utf-8-sig')
        for marker in ['team-development-standard', 'development-workflow']:
            if '<!-- ' + marker + ':managed:' in content:
                findings.append(agents.name+':' + marker)
    config = home / 'config.toml'
    if config.is_file():
        # Detection only. Do not parse, print, or rewrite credentials and settings.
        content = config.read_text(encoding='utf-8-sig')
        for name in ['team_harness', 'development_workflow']:
            if re.search(r'(?m)^\s*\[\s*["\']?mcp_servers["\']?\s*\.\s*["\']?' + name + r'["\']?\s*(?:\.|\])', content):
                findings.append('config.toml:' + name)
    if edition == 'claude':
        import os
        config = (Path.home() / '.claude.json' if home == (Path.home() / '.claude').resolve()
                  and not os.environ.get('CLAUDE_CONFIG_DIR') else home / '.claude.json')
        no_links(config)
        if config.is_file():
            servers = json.loads(config.read_text(encoding='utf-8-sig')).get('mcpServers', {})
            for name in ['team_harness', 'development_workflow']:
                if name in servers:
                    findings.append('.claude.json:' + name)
    return findings
