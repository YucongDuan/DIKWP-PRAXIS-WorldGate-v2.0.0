"""Strict local serialization and content addressing. Hashes are not attestations."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

MAX_BYTES = 8_000_000

class ValidationError(ValueError):
    pass

def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValidationError(f"Duplicate JSON key: {k}")
        out[k] = v
    return out

def loads(raw: str | bytes) -> Any:
    if len(raw.encode('utf-8') if isinstance(raw, str) else raw) > MAX_BYTES:
        raise ValidationError("Input exceeds 8 MB limit")
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValidationError(f"Non-finite: {x}")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(str(exc)) from exc

def canonical(obj: Any) -> bytes:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Not finite JSON: {exc}") from exc

def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()

def load(path) -> Any:
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ValidationError("Input exceeds 8 MB limit")
    return loads(p.read_bytes())

def save(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    canonical(obj)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')

def read_jsonl(path):
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ValidationError("JSONL exceeds 8 MB")
    return [loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def write_jsonl(path, rows):
    Path(path).write_text(''.join(canonical(row).decode('utf-8') + '\n' for row in rows), encoding='utf-8')

def number(value, name, low=None, high=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{name}: finite number required")
    if integer and not isinstance(value, int):
        raise ValidationError(f"{name}: integer required")
    if low is not None and value < low or high is not None and value > high:
        raise ValidationError(f"{name}: outside bounds [{low}, {high}]")
    return value

def nonempty(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValidationError(f"{name}: nonempty string (<=500 chars) required")
    return value

def field(obj, dotted):
    cur = obj
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur

def new_output(path):
    p = Path(path)
    if p.exists():
        raise ValidationError("Output already exists. Use a new directory; no silent overwrite.")
    p.mkdir(parents=True)
    return p

def file_manifest(folder):
    root = Path(folder)
    files = []
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts:
            files.append({'path': p.relative_to(root).as_posix(), 'size': p.stat().st_size,
                          'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    return {'files': files, 'root_hash': digest(files),
            'boundary': 'Integrity only; authentic origin requires an independently trusted anchor.'}

def verify_manifest(folder):
    expected = load(Path(folder) / 'manifest.json')
    actual = file_manifest(folder)
    return actual == expected

def chained(events):
    prev = '0' * 64
    result = []
    for seq, event in enumerate(events, 1):
        row = {'seq': seq, 'previous': prev, 'event': event}
        row['hash'] = digest(row)
        result.append(row)
        prev = row['hash']
    return result

def verify_chain(rows, expected_tail=None, expected_count=None):
    prev = '0' * 64
    for n, row in enumerate(rows, 1):
        if set(row) != {'seq','previous','event','hash'}:
            return False
        body = {k: row[k] for k in ['seq','previous','event']}
        if row['seq'] != n or row['previous'] != prev or digest(body) != row['hash']:
            return False
        prev = row['hash']
    return (expected_tail is None or expected_tail == prev) and (expected_count is None or expected_count == len(rows))
