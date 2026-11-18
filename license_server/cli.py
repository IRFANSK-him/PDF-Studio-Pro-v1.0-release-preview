"""Provision local server and inspect/manage licenses without exporting private secrets."""
import argparse
import json
import secrets
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .core import save_private_key, public_pem


def main():
    p = argparse.ArgumentParser(description='PDF Studio Pro license infrastructure')
    p.add_argument('command', choices=['init', 'show-admin-token'])
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--base-url', default='http://127.0.0.1:8765')
    args = p.parse_args()
    root = args.root.resolve()
    private_path = root / 'secrets/license_private.pem'
    admin_path = root / 'secrets/admin_token.txt'
    config_path = root / 'config/license_client.json'
    if args.command == 'show-admin-token':
        if not admin_path.is_file():
            p.error('Provision server first')
        print(admin_path.read_text().strip())
        return
    url = urlparse(args.base_url)
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')):
        p.error('Use HTTPS for remote license server URLs; plain HTTP only allowed on localhost')
    if not private_path.exists():
        save_private_key(Ed25519PrivateKey.generate(), private_path)
        print('Generated Ed25519 server signing key (private; do not distribute).')
    if not admin_path.exists():
        admin_path.parent.mkdir(parents=True, exist_ok=True)
        with admin_path.open('x') as f:
            f.write(secrets.token_urlsafe(40))
        admin_path.chmod(0o600)
        print('Generated admin token (private; do not distribute).')
    from .core import load_private_key
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        'server_url': args.base_url.rstrip('/'),
        'server_public_key_pem': public_pem(load_private_key(private_path)).decode(),
    }, indent=2), encoding='utf-8')
    print(f'Client public config: {config_path}')
    print(f'Server private key: {private_path} (NEVER package with desktop app)')
    print('Run scripts/start_local_license_server.bat and create a license using admin_cli.py')


if __name__ == '__main__':
    main()
