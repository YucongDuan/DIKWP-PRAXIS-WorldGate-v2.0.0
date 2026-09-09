# SPDX-License-Identifier: Apache-2.0
"""Ed25519 using PyCA cryptography. No custom crypto or insecure fallback.
Configured public keys identify local roles, not natural persons or institutions.
"""
from __future__ import annotations
import base64, os
from pathlib import Path
from .common import Rejected, canonical, digest, fields, ident
DOMAIN = b'PRAXIS-WORLDGATE-v2\x00'
ROLES = ('owner', 'evaluator', 'reviewer', 'operator', 'executor', 'observer')

def backend():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization
        from cryptography.exceptions import InvalidSignature
    except ImportError as e:
        raise Rejected('CRYPTO_BACKEND_REQUIRED', 'Install cryptography; no insecure fallback is provided.') from e
    return (Ed25519PrivateKey, Ed25519PublicKey, serialization, InvalidSignature)

def generate():
    pri, _, s, _ = backend()
    k = pri.generate()
    return (k.private_bytes(s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption()), base64.b64encode(k.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)).decode())

def keyfile(p):
    raw, public = generate()
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 384)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
    return {'public_key': public, 'key_id': 'key-' + digest(public)[:24], 'warning': 'Plaintext private key; protect with OS controls or a key manager.'}

def sign(payload, private, key_id):
    ident(key_id)
    pri, _, _, _ = backend()
    body = {'key_id': key_id, 'payload': payload}
    return {**body, 'signature': base64.b64encode(pri.from_private_bytes(private).sign(DOMAIN + canonical(body))).decode()}

def validate_trust(t):
    if not isinstance(t, dict) or not t:
        raise Rejected('TRUST_REQUIRED')
    seen = set()
    for kid, e in t.items():
        ident(kid)
        fields(e, ('principal', 'tenant', 'roles', 'public_key'))
        ident(e['principal'])
        ident(e['tenant'])
        if not isinstance(e['roles'], list) or not e['roles'] or any((r not in ROLES for r in e['roles'])):
            raise Rejected('TRUST_ROLES')
        try:
            b = base64.b64decode(e['public_key'], validate=True)
        except (ValueError, TypeError) as ex:
            raise Rejected('TRUST_KEY') from ex
        if len(b) != 32:
            raise Rejected('TRUST_KEY')
        if b in seen:
            raise Rejected('DUPLICATE_TRUST_KEY')
        seen.add(b)
    return t

def verify(env, trust, role, tenant):
    fields(env, ('key_id', 'payload', 'signature'))
    e = trust.get(env['key_id'])
    if not e or role not in e['roles'] or e['tenant'] != tenant:
        raise Rejected('UNTRUSTED_ROLE_OR_TENANT')
    _, pub, _, bad = backend()
    try:
        pub.from_public_bytes(base64.b64decode(e['public_key'], validate=True)).verify(base64.b64decode(env['signature'], validate=True), DOMAIN + canonical({'key_id': env['key_id'], 'payload': env['payload']}))
    except (bad, ValueError, TypeError) as ex:
        raise Rejected('BAD_SIGNATURE') from ex
    return e['principal']
