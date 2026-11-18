"""Refuse to embed loopback license endpoints in a public installer by default."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pdfstudio.licensing import read_client_config, ActivationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-local', action='store_true')
    args = parser.parse_args()
    try:
        url, _ = read_client_config(Path('config/license_client.json'))
        if not args.allow_local and not url.startswith('https://'):
            raise ValueError('Release must point to a live HTTPS license server; local-only builds '
                             'require --allow-local for development.')
        print('Release config valid:', url)
    except (ValueError, ActivationError) as exc:
        sys.exit('Build blocked: ' + str(exc))


if __name__ == '__main__':
    main()
