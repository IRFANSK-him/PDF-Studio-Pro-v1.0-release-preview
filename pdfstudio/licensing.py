"""Online-first license client with public-key verification and per-PC identity.

Never include the API private signing key or admin token in this client module.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from license_server.core import verify_token


class ActivationError(Exception):
    pass


def device_fingerprint(machine_seed: str | None = None) -> str:
    """Stable pseudonymous fingerprint; Windows MachineGuid is local only.

    This is a software binding, not hardware-backed attestation; cloning and
    spoofing by a motivated user is possible. The raw MachineGuid is NEVER sent.
    """
    if machine_seed is None:
        if sys.platform != 'win32':
            raise ActivationError('This desktop license binding requires Windows.')
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as key:
                machine_seed = winreg.QueryValueEx(key, 'MachineGuid')[0]
        except OSError as exc:
            raise ActivationError('Could not read this PC’s Windows MachineGuid.') from exc
    if not machine_seed:
        raise ActivationError('Could not identify this PC')
    return hashlib.sha256(('PDFStudioPro:Windows-PC:v1:' + machine_seed).encode()).hexdigest()


def user_data_dir() -> Path:
    if sys.platform == 'win32':
        return Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'PDFStudioPro'
    return Path.home() / '.pdfstudiopro-test'


def client_config_path() -> Path:
    override = os.getenv('PDFSP_CLIENT_CONFIG')
    if override:
        return Path(override)
    candidates = [Path(sys.executable).resolve().parent / 'config/license_client.json']
    if getattr(sys, 'frozen', False):
        candidates.append(Path(sys._MEIPASS) / 'config/license_client.json')
    candidates.append(Path(__file__).resolve().parent.parent / 'config/license_client.json')
    for p in candidates:
        if p.is_file():
            return p
    return candidates[-1]


def read_client_config(path: Path) -> tuple[str, Ed25519PublicKey]:
    try:
        cfg = json.loads(path.read_text(encoding='utf-8'))
        url = cfg['server_url'].rstrip('/')
        parsed = urlparse(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('Invalid server URL')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError('Remote servers must use HTTPS')
        pub = serialization.load_pem_public_key(cfg['server_public_key_pem'].encode())
        if not isinstance(pub, Ed25519PublicKey):
            raise ValueError('Incorrect public key type')
        return url, pub
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ActivationError(f'License configuration is missing or invalid: {exc}') from exc


class LicenseManager:
    def __init__(self, config_path: Path | None = None,
                 state_path: Path | None = None, http_client=None,
                 machine_seed: str | None = None):
        self.config_path = config_path or client_config_path()
        self.server_url, self.public_key = read_client_config(self.config_path)
        self.state_path = state_path or (user_data_dir() / 'activation.json')
        self.http = http_client or httpx.Client(timeout=5.0, follow_redirects=False)
        self.device_hash = device_fingerprint(machine_seed)

    def _post(self, endpoint: str, body: dict) -> dict:
        try:
            resp = self.http.post(self.server_url + endpoint, json=body)
            if resp.status_code != 200:
                error = resp.json().get('detail', f'HTTP {resp.status_code}')
                raise ActivationError(f'License server: {str(error)[:180]}')
            return resp.json()
        except ActivationError:
            raise
        except (httpx.RequestError, ValueError, KeyError) as exc:
            raise ActivationError(f'License server is unavailable or returned invalid data: {exc}') from exc

    def _validate_local_token(self, token: str):
        try:
            claims = verify_token(self.public_key, token)
            if claims.get('ver') != 1 or claims.get('entitlement') != 'lifetime' \
               or claims.get('device_hash') != self.device_hash or not isinstance(claims.get('license_id'), int):
                raise ValueError('Token does not match this Windows PC')
            return claims
        except ValueError as exc:
            raise ActivationError('Invalid, modified or wrong-PC activation token') from exc

    def _save_token(self, token: str):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({'token': token}, indent=2)
        fd, staging = tempfile.mkstemp(prefix='activation-', dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(data)
            os.replace(staging, self.state_path)
        finally:
            if os.path.exists(staging):
                os.unlink(staging)

    def activate(self, key: str) -> dict:
        if not re.fullmatch(r'[A-Za-z0-9-]{15,100}', key.strip()):
            raise ActivationError('Enter a valid license key')
        result = self._post('/v1/activate', {'license_key': key.strip(),
                'device_hash': self.device_hash, 'device_label': platform.node()[:80]})
        token = result.get('token', '')
        self._validate_local_token(token)
        checked = self._post('/v1/verify', {'token': token, 'device_hash': self.device_hash})
        if checked.get('valid') is not True:
            raise ActivationError('Activation not confirmed by license server')
        self._save_token(token)
        return checked

    def verify(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            token = state['token']
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ActivationError('No valid activation on this PC') from exc
        self._validate_local_token(token)
        response = self._post('/v1/verify', {'token': token, 'device_hash': self.device_hash})
        if response.get('valid') is not True:
            raise ActivationError('License verification failed')
        return response

    def clear_local_activation(self):
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass
