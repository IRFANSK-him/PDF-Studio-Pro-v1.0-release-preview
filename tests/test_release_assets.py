"""Static release safety checks; not a substitute for Windows installer testing."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_public_client_configuration_not_preprovisioned():
    assert not (ROOT/'config/license_client.json').exists(), 'No live endpoint/public key in source-only ZIP'
    assert not (ROOT/'secrets').exists(), 'Never package server signing keys or the admin token'
    assert (ROOT/'config/license_client.example.json').is_file()


def test_windows_installer_and_build_assets():
    assert (ROOT/'assets/pdfstudio.ico').read_bytes()[:4] == b'\x00\x00\x01\x00'
    script = (ROOT/'installer/PDFStudioPro.iss').read_text()
    assert 'PrivilegesRequired=lowest' in script
    assert 'PDF-Studio-Pro.exe' in script
    for name in ('build_windows_portable.bat', 'build_windows_installer.bat',
                 'start_local_license_server.bat','setup_windows.bat','test_windows.bat'):
        assert (ROOT/'scripts'/name).is_file()
    assert 'release_preflight.py' in (ROOT/'scripts/build_windows_portable.bat').read_text()


def test_preflight_refuses_unconfigured_client():
    from subprocess import run
    import sys
    resp = run([sys.executable, str(ROOT/'scripts/release_preflight.py')], cwd=ROOT,
               capture_output=True, text=True)
    assert resp.returncode != 0
    assert 'Build blocked' in resp.stderr
