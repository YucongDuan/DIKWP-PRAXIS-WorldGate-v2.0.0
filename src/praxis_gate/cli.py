# SPDX-License-Identifier: Apache-2.0
"""Local operator CLI. It never accepts a client-supplied clock or arbitrary commands."""
from __future__ import annotations
import argparse, os, sys, time, sqlite3
from pathlib import Path
from .common import Rejected, canonical, load, save, fresh, digest
from .signing import keyfile, sign, ROLES
from .kernel import WorldGate, observe_readonly
from .replay import replay_world
from .monitor import monitor
from .experiments import demo
from .fixtures import Fixture

def write_new(path, obj):
    if Path(path).exists():
        raise Rejected('OUTPUT_EXISTS', str(path))
    save(path, obj)

def init_project(out):
    root = fresh(out)
    trust = {}
    for role in ROLES:
        info = keyfile(root / 'keys' / (role + '.key'))
        trust[info['key_id']] = {'principal': role + '-person', 'tenant': 'local', 'roles': [role], 'public_key': info['public_key']}
        save(root / 'keys' / (role + '.public.json'), info)
    save(root / 'trust.json', trust)
    WorldGate.create(root / 'world.sqlite', trust, [{'tenant': 'local', 'resource': 'stock-a', 'units': 100}])
    now = int(time.time())
    candidate = digest('replace-with-reviewed-candidate-build-manifest')
    contract = {'kind': 'contract', 'tenant': 'local', 'owner': 'owner-person', 'contract_id': 'my-contract', 'candidate_hash': candidate, 'operation': 'inventory.reserve', 'resources': ['stock-a'], 'min_remaining': 2, 'max_units_per_action': 20, 'issued_at': now, 'expires_at': now + 3600, 'max_lease_seconds': 300}
    save(root / 'contract.json', contract)
    (root / 'README.txt').write_text('LOCAL SANDBOX ONLY\nKeys for all six roles are co-located here for setup, NOT independent human approvals.\nMove each private key into separate custody before a team pilot.\nUse the sign command, then contract/evidence/grant/prepare/commit/observe/attest.\nNo grant or side effect has been created by init.\nTemplate timestamps expire; regenerate intentionally, do not bypass clock checks.\n', encoding='utf-8')
    return {'output': str(root), 'state': 'LOCAL_SANDBOX_INITIALIZED', 'grants_created': 0, 'warning': 'Private keys are plaintext and co-located; do not use as organizational separation.'}

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'legacy':
        from praxis_os.cli import main as old
        return old(argv[1:])
    ap = argparse.ArgumentParser(prog='praxis-worldgate')
    ap.add_argument('--version', action='version', version='2.0.0')
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('inspect')
    a = sp.add_parser('demo')
    a.add_argument('--out', required=True)
    a.add_argument('--skip-legacy', action='store_true')
    a = sp.add_parser('init')
    a.add_argument('--out', required=True)
    a = sp.add_parser('keygen')
    a.add_argument('--key', required=True)
    a.add_argument('--out', required=True)
    a = sp.add_parser('sign')
    a.add_argument('payload')
    a.add_argument('--key', required=True)
    a.add_argument('--key-id', required=True)
    a.add_argument('--out', required=True)
    for cmd in ('contract', 'evidence', 'grant', 'prepare', 'commit', 'attest', 'compensate', 'revoke'):
        a = sp.add_parser(cmd)
        a.add_argument('envelope')
        a.add_argument('--db', required=True)
        a.add_argument('--out')
    a = sp.add_parser('observe')
    a.add_argument('--db', required=True)
    a.add_argument('--tenant', required=True)
    a.add_argument('--action', required=True)
    a.add_argument('--key', required=True)
    a.add_argument('--key-id', required=True)
    a.add_argument('--out', required=True)
    a = sp.add_parser('export')
    a.add_argument('--db', required=True)
    a.add_argument('--out', required=True)
    a = sp.add_parser('anchor')
    a.add_argument('--db', required=True)
    a.add_argument('--tenant', required=True)
    a.add_argument('--key', required=True)
    a.add_argument('--key-id', required=True)
    a.add_argument('--out', required=True)
    a = sp.add_parser('replay')
    a.add_argument('world')
    a.add_argument('--anchor')
    a.add_argument('--trust')
    a.add_argument('--out')
    a = sp.add_parser('monitor')
    a.add_argument('config')
    a.add_argument('observations')
    a.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    try:
        if getattr(args, 'out', None) and Path(args.out).exists():
            raise Rejected('OUTPUT_EXISTS', args.out)
        if args.cmd == 'inspect':
            r = {'system': 'DIKWP-PRAXIS-OS', 'edition': 'WORLDGATE', 'version': '2.0.0', 'adapter': 'inventory.reserve (local SQLite only)', 'direct_dependency': 'cryptography', 'external_action_connector': False, 'aggregate_safety_score': None, 'requires_trusted_host_and_clock': True, 'legacy_cli': 'legacy <v1 command>', 'warnings': ['No sandbox for untrusted code.', 'Configured signature keys are not human identity verification.', 'Passing evidence does not issue a grant.']}
        elif args.cmd == 'demo':
            s = demo(args.out, not args.skip_legacy)
            r = {'output': args.out, 'runtime_cases': s['runtime']['cases'], 'runtime_passed': s['runtime']['passed'], 'legacy': s['legacy']}
        elif args.cmd == 'init':
            r = init_project(args.out)
        elif args.cmd == 'keygen':
            r = keyfile(args.key)
            write_new(args.out, r)
        elif args.cmd == 'sign':
            r = sign(load(args.payload), Path(args.key).read_bytes(), args.key_id)
            write_new(args.out, r)
        elif args.cmd in ('contract', 'evidence', 'grant', 'prepare', 'commit', 'attest', 'compensate', 'revoke'):
            r = WorldGate(args.db).apply('observe' if args.cmd == 'attest' else args.cmd, load(args.envelope))
            if args.out:
                write_new(args.out, r)
        elif args.cmd == 'observe':
            r = observe_readonly(args.db, args.tenant, args.action, Path(args.key).read_bytes(), args.key_id)
            write_new(args.out, r)
        elif args.cmd == 'export':
            r = WorldGate(args.db).export()
            write_new(args.out, r)
        elif args.cmd == 'anchor':
            r = WorldGate(args.db).anchor(Path(args.key).read_bytes(), args.key_id, args.tenant)
            write_new(args.out, r)
        elif args.cmd == 'replay':
            r = replay_world(load(args.world), load(args.anchor) if args.anchor else None, load(args.trust) if args.trust else None)
            if args.out:
                write_new(args.out, r)
        else:
            r = monitor(load(args.config), load(args.observations))
            write_new(args.out, r)
        print(canonical(r).decode())
        return 0
    except (Rejected, OSError, ValueError, TypeError, KeyError, sqlite3.Error) as e:
        print(canonical({'error': getattr(e, 'code', type(e).__name__), 'message': str(e)}).decode(), file=sys.stderr)
        return 2
