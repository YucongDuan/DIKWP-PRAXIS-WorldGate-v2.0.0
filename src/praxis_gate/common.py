# SPDX-License-Identifier: Apache-2.0
"""Strict finite JSON and local content addressing; hashes are not signatures."""
from __future__ import annotations
import hashlib, json, math, re
from pathlib import Path
LIMIT = 8000000

class Rejected(ValueError):

    def __init__(self, code, detail=''):
        self.code = code
        self.detail = detail
        super().__init__(code + (': ' + detail if detail else ''))

def fields(x, required, optional=()):
    if not isinstance(x, dict):
        raise Rejected('OBJECT_REQUIRED')
    if set(required) - x.keys() or x.keys() - set(required) - set(optional):
        raise Rejected('SCHEMA_FIELDS')
    return x

def ident(x):
    if not isinstance(x, str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,120}', x):
        raise Rejected('IDENTIFIER')
    return x

def integer(x, lo=0, hi=2 ** 40):
    if type(x) is not int or not lo <= x <= hi:
        raise Rejected('INTEGER_RANGE')
    return x

def hexhash(x):
    if not isinstance(x, str) or not re.fullmatch('[0-9a-f]{64}', x):
        raise Rejected('HASH_FORMAT')
    return x

def prob(x, strict=False):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or (not math.isfinite(x)) or (not (0 < x < 1 if strict else 0 <= x <= 1)):
        raise Rejected('PROBABILITY')
    return float(x)

def canonical(x):
    try:
        b = json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError) as e:
        raise Rejected('FINITE_JSON') from e
    if len(b) > LIMIT:
        raise Rejected('SIZE_LIMIT')
    return b

def digest(x):
    return hashlib.sha256(canonical(x)).hexdigest()

def _pairs(xs):
    out = {}
    for k, v in xs:
        if k in out:
            raise Rejected('DUPLICATE_JSON_KEY', k)
        out[k] = v
    return out

def loads(b):
    if len(b.encode() if isinstance(b, str) else b) > LIMIT:
        raise Rejected('SIZE_LIMIT')
    try:
        return json.loads(b, object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(Rejected('NONFINITE_JSON')))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as e:
        raise Rejected('BAD_JSON') from e

def load(p):
    return loads(Path(p).read_bytes())

def save(p, x):
    canonical(x)
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')

def fresh(p):
    p = Path(p)
    if p.exists():
        raise Rejected('OUTPUT_EXISTS', str(p))
    p.mkdir(parents=True)
    return p

def interval(now, issued, expires, max_duration=86400):
    integer(now)
    integer(issued)
    integer(expires)
    if not issued <= now < expires:
        raise Rejected('TIME_WINDOW')
    if expires - issued > max_duration:
        raise Rejected('LEASE_TOO_LONG')

def manifest(root):
    p = Path(root)
    r = [{'path': f.relative_to(p).as_posix(), 'bytes': f.stat().st_size, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(p.rglob('*')) if f.is_file() and '__pycache__' not in f.parts and (f.name != 'manifest.json')]
    return {'files': r, 'root_hash': digest(r), 'meaning': 'Integrity requires an independently trusted root.'}
