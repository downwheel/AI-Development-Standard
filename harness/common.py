"""Shared bounded values and errors. No filesystem side effects on import."""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

class HarnessError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

def fail(code, message):
    raise HarnessError(code, message)

def now():
    return datetime.now(timezone.utc).isoformat()

def uid(prefix):
    return prefix + '-' + uuid.uuid4().hex

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def identifier(value, label='id'):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,95}', value):
        fail('invalid_identifier', f'{label} must contain 1-96 lowercase letters, digits, - or _.')
    return value

def emit(state, kind, data):
    event = {'event_id': uid('event'), 'at': now(), 'kind': kind, 'data': data}
    state.setdefault('events', []).append(event)
    return event

def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        fail('invalid_path', 'Use a nonempty relative path with forward slashes.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value:
        fail('invalid_path', 'Path must be normalized and relative.')
    for part in path.parts:
        if part.endswith((' ', '.')) or re.search(r'[<>"|?*\x00-\x1f]', part):
            fail('invalid_path', 'Unsupported path characters.')
        if part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
            fail('invalid_path', 'Reserved device name.')
    return path

def scan_secrets(raw):
    text = raw.decode('utf-8', errors='replace')
    patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                r'\bAKIA[0-9A-Z]{16}\b', r'\bgh[pousr]_[A-Za-z0-9]{30,}\b',
                r'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b']
    if any(re.search(pattern, text) for pattern in patterns):
        fail('secret_content', 'Potential credential detected; raw value omitted.')
    return raw

def overlap(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a in b.parents or b in a.parents
