"""Server-side, transactional, single-PC lifetime-license management."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def decode64(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError('Invalid signature encoding')
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def normalize_key(key: str) -> str:
    return key.strip().upper().replace(' ', '')


def key_digest(key: str) -> str:
    return hashlib.sha256(normalize_key(key).encode('ascii')).hexdigest()


def new_license_key() -> str:
    # 160 bits from a cryptographically secure generator. Store the hash only.
    raw = secrets.token_hex(20).upper()
    return 'PSP-' + '-'.join(raw[i:i+8] for i in range(0, 40, 8))


def public_pem(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def save_private_key(private: Ed25519PrivateKey, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = private.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with path.open('xb') as f:
        os.chmod(path, 0o600)
        f.write(data)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Only Ed25519 signing keys supported')
    return key


def sign_token(private: Ed25519PrivateKey, claims: dict) -> str:
    body = b64url(json.dumps(claims, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    signature = b64url(private.sign(body.encode('ascii')))
    return f'{body}.{signature}'


def verify_token(public: Ed25519PublicKey, token: str) -> dict:
    try:
        if len(token) > 8192:
            raise ValueError('Oversized token')
        body, sig = token.split('.')
        public.verify(decode64(sig), body.encode('ascii'))
        claims = json.loads(decode64(body))
        if not isinstance(claims, dict) or claims.get('iss') != 'PDF-Studio-Pro':
            raise ValueError('Invalid claims')
        return claims
    except (ValueError, TypeError, InvalidSignature, json.JSONDecodeError, binascii.Error, UnicodeError) as exc:
        raise ValueError('Invalid signed license token') from exc


@dataclass(frozen=True)
class ServerSettings:
    database: Path
    signing_key: Path
    admin_token: str


class LicenseStore:
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.private = load_private_key(settings.signing_key)
        self.public = self.private.public_key()
        self.settings.database.parent.mkdir(parents=True, exist_ok=True)
        self.create_schema()

    def db(self):
        conn = sqlite3.connect(str(self.settings.database), timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=20000')
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    def create_schema(self):
        with self.db() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
                    device_hash TEXT,
                    device_label TEXT,
                    generation INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    activated_at INTEGER,
                    last_verified_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_id INTEGER NOT NULL REFERENCES licenses(id),
                    event TEXT NOT NULL,
                    happened_at INTEGER NOT NULL
                );
            ''')

    @staticmethod
    def _audit(db, license_id: int, event: str):
        db.execute('INSERT INTO audit (license_id,event,happened_at) VALUES(?,?,?)',
                   (license_id, event, int(time.time())))

    def create_license(self) -> dict:
        for _ in range(3):
            key = new_license_key()
            try:
                with self.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    cur = db.execute('INSERT INTO licenses(key_hash,created_at) VALUES (?,?)',
                                     (key_digest(key), int(time.time())))
                    self._audit(db, cur.lastrowid, 'created')
                    db.commit()
                    return {'id': cur.lastrowid, 'license_key': key, 'license_type': 'lifetime'}
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError('Could not generate unique license')

    def list_licenses(self) -> list[dict]:
        with self.db() as db:
            rows = db.execute('SELECT id,status,device_hash,device_label,generation,created_at,'
                              'activated_at,last_verified_at FROM licenses ORDER BY id DESC').fetchall()
            return [dict(row) for row in rows]

    def audit_events(self, license_id: int) -> list[dict]:
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT event,happened_at FROM audit '
                     'WHERE license_id=? ORDER BY id DESC LIMIT 100', (license_id,))]

    def activate(self, key: str, device: str, label: str) -> str:
        digest = key_digest(key)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM licenses WHERE key_hash=?', (digest,)).fetchone()
            if row is None:
                raise LicenseError(401, 'Invalid license key')
            if row['status'] != 'active':
                raise LicenseError(403, 'License revoked')
            if row['device_hash'] and not hmac.compare_digest(row['device_hash'], device):
                self._audit(db, row['id'], 'rejected_other_device')
                db.commit()
                raise LicenseError(409, 'License already activated on another PC')
            now = int(time.time())
            db.execute('UPDATE licenses SET device_hash=?, device_label=?, '
                       'activated_at=COALESCE(activated_at, ?) WHERE id=?',
                       (device, label[:80], now, row['id']))
            self._audit(db, row['id'], 'activated')
            db.commit()
            return sign_token(self.private, {'iss': 'PDF-Studio-Pro', 'ver': 1, 'license_id': row['id'],
                          'device_hash': device, 'generation': row['generation'],
                          'entitlement': 'lifetime', 'iat': now})

    def verify(self, token: str, device: str) -> dict:
        try:
            claims = verify_token(self.public, token)
        except ValueError as exc:
            raise LicenseError(401, str(exc)) from exc
        if claims.get('ver') != 1 or claims.get('entitlement') != 'lifetime':
            raise LicenseError(401, 'Invalid entitlement')
        if not hmac.compare_digest(str(claims.get('device_hash', '')), device):
            raise LicenseError(403, 'Token belongs to a different PC')
        with self.db() as db:
            row = db.execute('SELECT * FROM licenses WHERE id=?', (claims.get('license_id'),)).fetchone()
            if not row or row['status'] != 'active' or row['device_hash'] != device \
               or row['generation'] != claims.get('generation'):
                raise LicenseError(403, 'License revoked, reset or no longer valid')
            db.execute('UPDATE licenses SET last_verified_at=? WHERE id=?',
                       (int(time.time()), row['id']))
            return {'valid': True, 'license_type': 'lifetime', 'license_id': row['id']}

    def manage(self, license_id: int, operation: str):
        if operation not in ('revoke', 'reset-device', 'restore'):
            raise ValueError('Unknown operation')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id,status FROM licenses WHERE id=?', (license_id,)).fetchone()
            if not row:
                raise LicenseError(404, 'License not found')
            if operation == 'reset-device':
                if row['status'] != 'active':
                    raise LicenseError(409, 'Cannot reset a revoked license; restore it first')
                db.execute('UPDATE licenses SET device_hash=NULL,device_label=NULL, '
                           'activated_at=NULL,generation=generation+1 WHERE id=?', (license_id,))
            elif operation == 'revoke':
                db.execute("UPDATE licenses SET status='revoked',generation=generation+1 WHERE id=?",
                           (license_id,))
            else:
                db.execute("UPDATE licenses SET status='active',generation=generation+1, "
                           "device_hash=NULL,device_label=NULL,activated_at=NULL WHERE id=?", (license_id,))
            self._audit(db, license_id, operation)
            db.commit()
            return {'id': license_id, 'operation': operation, 'ok': True}


class LicenseError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
