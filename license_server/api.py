"""FastAPI licensing endpoints. Never mount an admin endpoint without a real secret."""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .core import LicenseError, LicenseStore, ServerSettings

DEVICE_PATTERN = r'^[a-f0-9]{64}$'


class ActivationRequest(BaseModel):
    license_key: str = Field(min_length=15, max_length=100, pattern=r'^[A-Za-z0-9-]+$')
    device_hash: str = Field(pattern=DEVICE_PATTERN)
    device_label: str = Field(default='', max_length=80)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=8192)
    device_hash: str = Field(pattern=DEVICE_PATTERN)


def get_settings():
    root = Path(os.getenv('PDFSP_SERVER_ROOT', '.')).resolve()
    token_file = root / 'secrets/admin_token.txt'
    token = os.getenv('PDFSP_ADMIN_TOKEN') or (token_file.read_text().strip() if token_file.exists() else '')
    return ServerSettings(
        database=Path(os.getenv('PDFSP_DATABASE', str(root / 'secrets/licenses.sqlite3'))),
        signing_key=Path(os.getenv('PDFSP_SIGNING_KEY', str(root / 'secrets/license_private.pem'))),
        admin_token=token,
    )


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if len(settings.admin_token) < 32:
        raise RuntimeError('Set a cryptographically random admin token of at least 32 characters')
    store = LicenseStore(settings)
    app = FastAPI(title='PDF Studio Pro License API', version='1.0.0',
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def admin(authorization: str | None = Header(default=None)):
        candidate = (authorization or '').removeprefix('Bearer ').strip()
        if not hmac.compare_digest(candidate, settings.admin_token):
            raise HTTPException(401, 'Administrator authentication required')

    def wrap(action, *args):
        try:
            return action(*args)
        except LicenseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @app.get('/v1/health')
    def health():
        return {'status': 'ok'}

    @app.post('/v1/activate')
    def activate(data: ActivationRequest):
        return {'token': wrap(store.activate, data.license_key,
                              data.device_hash, data.device_label), 'license_type': 'lifetime'}

    @app.post('/v1/verify')
    def verify(data: VerifyRequest):
        return wrap(store.verify, data.token, data.device_hash)

    @app.post('/v1/admin/licenses', dependencies=[Depends(admin)])
    def create_license():
        return store.create_license()

    @app.get('/v1/admin/licenses', dependencies=[Depends(admin)])
    def list_licenses():
        return {'licenses': store.list_licenses()}

    @app.get('/v1/admin/licenses/{license_id}/audit', dependencies=[Depends(admin)])
    def audit(license_id: int):
        return {'events': store.audit_events(license_id)}

    @app.post('/v1/admin/licenses/{license_id}/revoke', dependencies=[Depends(admin)])
    def revoke(license_id: int):
        return wrap(store.manage, license_id, 'revoke')

    @app.post('/v1/admin/licenses/{license_id}/reset-device', dependencies=[Depends(admin)])
    def reset(license_id: int):
        return wrap(store.manage, license_id, 'reset-device')

    @app.post('/v1/admin/licenses/{license_id}/restore', dependencies=[Depends(admin)])
    def restore(license_id: int):
        return wrap(store.manage, license_id, 'restore')

    return app


# ASGI import target: uvicorn license_server.api:app
# Provisioning MUST happen before importing this module in a live server.
app = create_app() if os.getenv('PDFSP_DISABLE_AUTOAPP') != '1' else None
