"""Local/remote license admin CLI via authenticated HTTP. Avoid putting tokens on command lines."""
import argparse
import getpass
import json
import os
from urllib.parse import urlparse
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description='PDF Studio Pro license administration')
    parser.add_argument('command', choices=['create', 'list', 'revoke', 'reset-device', 'restore', 'audit'])
    parser.add_argument('--id', type=int)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--admin-token', default=None, help='Use PDFSP_ADMIN_TOKEN env instead, to avoid shell history')
    args = parser.parse_args()
    if args.command in ('revoke', 'reset-device', 'restore', 'audit') and not args.id:
        parser.error('--id is required for this command')
    token_file = Path('secrets/admin_token.txt')
    token = args.admin_token or os.getenv('PDFSP_ADMIN_TOKEN') or (token_file.read_text().strip() if token_file.exists() else '')
    if not token:
        token = getpass.getpass('Admin token: ')
    parsed = urlparse(args.url)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        parser.error('Admin API requires HTTPS outside localhost')
    path = '/v1/admin/licenses'
    if args.command == 'create':
        method = 'POST'
    elif args.command == 'list':
        method = 'GET'
    else:
        method = 'GET' if args.command == 'audit' else 'POST'
        path += f'/{args.id}/{args.command}'
    resp = httpx.request(method, args.url.rstrip('/') + path,
                         headers={'Authorization': 'Bearer ' + token}, timeout=10.0)
    print(json.dumps(resp.json(), indent=2))
    resp.raise_for_status()


if __name__ == '__main__':
    main()
