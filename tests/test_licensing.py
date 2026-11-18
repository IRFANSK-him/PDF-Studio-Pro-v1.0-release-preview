"""Part 3 live API/client integration tests using isolated SQLite and real Ed25519."""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ['PDFSP_DISABLE_AUTOAPP'] = '1'

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from license_server.api import create_app
from license_server.core import ServerSettings, save_private_key, public_pem
from pdfstudio.licensing import LicenseManager, ActivationError, device_fingerprint, read_client_config


@pytest.fixture
def system(tmp_path):
    signing = tmp_path/'private.pem'
    secret = 'A' * 50
    save_private_key(Ed25519PrivateKey.generate(), signing)
    settings = ServerSettings(database=tmp_path/'licenses.sqlite3', signing_key=signing,
                              admin_token=secret)
    app = create_app(settings)
    http = TestClient(app)
    cfg = tmp_path/'client.json'
    cfg.write_text(json.dumps({
        'server_url': 'http://127.0.0.1:8765',
        'server_public_key_pem': public_pem(app.state.store.private).decode(),
    }))
    return app, http, cfg, tmp_path, secret


def admin(system, method='POST', path='/v1/admin/licenses'):
    return system[1].request(method, path, headers={'Authorization': 'Bearer ' + system[4]})


def new_key(system):
    r = admin(system)
    assert r.status_code == 200
    return r.json()


def manager(system, seed='PC-A'):
    return LicenseManager(system[2], system[3] / f'{seed}.json', system[1], seed)


def test_full_activation_verification_revocation(system):
    key = new_key(system)
    client = manager(system)
    with pytest.raises(ActivationError, match='No valid activation'):
        client.verify()
    assert client.activate(key['license_key'])['valid']
    assert client.verify()['license_type'] == 'lifetime'
    license_id = key['id']
    # A different machine cannot bind an already active key.
    second = manager(system, 'PC-B')
    with pytest.raises(ActivationError, match='already activated'):
        second.activate(key['license_key'])
    assert admin(system, path=f'/v1/admin/licenses/{license_id}/revoke').json()['ok']
    with pytest.raises(ActivationError, match='revoked'):
        client.verify()
    assert admin(system, path=f'/v1/admin/licenses/{license_id}/restore').json()['ok']
    # Restore deliberately invalidates old tokens and clears device binding.
    with pytest.raises(ActivationError):
        client.verify()
    assert second.activate(key['license_key'])['valid']
    assert second.verify()['valid']
    with pytest.raises(ActivationError):
        client.activate(key['license_key'])


def test_admin_reset_device_invalidates_old_token(system):
    key = new_key(system)
    a = manager(system)
    b = manager(system, 'PC-NEW')
    a.activate(key['license_key'])
    assert admin(system, path=f"/v1/admin/licenses/{key['id']}/reset-device").status_code == 200
    with pytest.raises(ActivationError, match='reset'):
        a.verify()
    assert b.activate(key['license_key'])['valid']
    with pytest.raises(ActivationError, match='another PC'):
        a.activate(key['license_key'])
    assert b.verify()['valid']


def test_admin_auth_key_storage_and_audit(system):
    resp = system[1].post('/v1/admin/licenses')
    assert resp.status_code == 401
    key = new_key(system)
    stored = system[0].state.store.list_licenses()
    assert stored[0]['id'] == key['id']
    assert key['license_key'] not in json.dumps(stored)
    assert 'key_hash' not in stored[0]
    assert admin(system, 'GET', f"/v1/admin/licenses/{key['id']}/audit").json()['events'][0]['event'] == 'created'
    assert system[1].post('/v1/activate', json={'license_key': 'WRONG-WRONG-WRONG',
               'device_hash': device_fingerprint('PC-A')}).status_code == 401


def test_signed_token_tampering_and_wrong_device(system):
    key = new_key(system)
    a = manager(system)
    a.activate(key['license_key'])
    state = json.loads(a.state_path.read_text())
    token = state['token']
    body, sig = token.split('.')
    state['token'] = body[:-1] + ('A' if body[-1] != 'A' else 'B') + '.' + sig
    a.state_path.write_text(json.dumps(state))
    with pytest.raises(ActivationError, match='Invalid'):
        a.verify()
    a.state_path.write_text(json.dumps({'token': token}))
    assert a.verify()['valid']
    b = manager(system, 'PC-C')
    b.state_path.write_text(json.dumps({'token': token}))
    with pytest.raises(ActivationError, match='wrong-PC'):
        b.verify()


def test_concurrent_activation_allows_exactly_one_device(system):
    key = new_key(system)
    barrier = threading.Barrier(6)
    def activate(i):
        barrier.wait()
        # New connection per client, one SQLite lock per activation transaction.
        with TestClient(system[0]) as c:
            return c.post('/v1/activate', json={'license_key': key['license_key'],
                'device_hash': device_fingerprint(f'PC-{i}'), 'device_label': f'PC-{i}'}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(activate, range(6)))
    assert statuses.count(200) == 1, statuses
    assert statuses.count(409) == 5, statuses


def test_config_https_policy_and_key_validation(tmp_path):
    invalid = tmp_path / 'config.json'
    invalid.write_text(json.dumps({'server_url': 'http://licenses.example.com',
      'server_public_key_pem': public_pem(Ed25519PrivateKey.generate()).decode()}))
    with pytest.raises(ActivationError, match='Remote servers must use HTTPS'):
        read_client_config(invalid)


def test_no_key_or_short_admin_secret(tmp_path):
    from license_server.api import create_app
    from license_server.core import ServerSettings
    with pytest.raises(RuntimeError, match='at least 32'):
        create_app(ServerSettings(tmp_path/'test.sqlite3', tmp_path/'missing.pem', 'short'))


def test_error_cases_are_rejected(system):
    key = new_key(system)
    a = manager(system)
    a.activate(key['license_key'])
    r = system[1].post('/v1/verify', json={'token': 'bad.token123',
                                           'device_hash': device_fingerprint('PC-A')})
    assert r.status_code == 401
    assert admin(system, path='/v1/admin/licenses/500000/reset-device').status_code == 404
    assert admin(system, path=f"/v1/admin/licenses/{key['id']}/revoke").status_code == 200
    assert admin(system, path=f"/v1/admin/licenses/{key['id']}/reset-device").status_code == 409
