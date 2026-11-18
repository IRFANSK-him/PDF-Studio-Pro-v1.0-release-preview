# PDF Studio Pro — Part 3 (v1.0 Source Candidate)

**The cumulative Part 1 + Part 2 + Part 3 codebase.** It includes the 30 originally requested features, an online-only activation flow for **lifetime / one Windows PC per license**, server-side verification and revocation, an administrator CLI, Windows portable build configuration, and an Inno Setup installer script. Source code is included; **no built Windows executable, hosted license service, payment system, or code-signing certificate is included.** The application has not yet passed Windows GUI and installer acceptance testing.

The UI remains based on `docs/approved-ui-reference.jpg` (dark header, red P icon, ribbon interface, thumbnail column, canvas, PDF Tools panel and bottom navigation). UI categories shown in the reference but not in the original approved scope (OCR, Forms, certificate signatures, Office export) are not implemented.

## Features

### Part 1 — Core PDF Application

Open/save multiple PDFs, page thumbnails, mouse drag-drop reorder, up/down reorder, undo/redo **page order**, page navigation, zoom, search/next match, crop, PDF to PNG, images to PDF, shortcuts, dark PySide6 UI.

### Part 2 — Editor / Security

Insert text and images, highlight, remove text/rectangles via **permanent PDF redaction**, text watermark, edit metadata, lossless compression, protect with passwords, and AES-256 encryption. Encryption refers to **PDF document protection**, separately from the online application license. See the Part 2 limitations in `docs/PDF_EDITOR_NOTES.md`.

### Part 3 — Licensing / Deployment

- **Online-only activation**; license server checked on *every launch*, and every **10 minutes** while the editor is open. Network/server failure causes fail-closed behavior.
- **Lifetime** entitlement: no product-license expiration. License server operations/hosting must remain available.
- **One PC per license:** Windows MachineGuid is hashed locally and the server stores only its SHA-256 derivative; a unique license may be activated on one PC at a time.
- **Server-signed activation tokens:** Ed25519. Public key ships in client config; server signing key and admin token are never bundled in the desktop build.
- **Revocation/restore and device reset:** administrator-only authenticated HTTP endpoints with generation counters that invalidate old tokens and permit a new PC after reset.
- **Audit events:** creation, activation, attempted activation on a different PC, revocation, restore, device reset. License keys are **hashed at rest** and displayed only when created.
- **Portable build** (`PyInstaller --onedir`) and **installer config** (Inno Setup 6, per-user install).

**Limitations:** This is software-based PC binding, not tamper-resistant hardware attestation. A determined attacker can modify a Python desktop application or spoof a fingerprint. There is no license-payment gateway or graphical admin portal. This sample backend uses SQLite; for significant production traffic, migrate to a managed database and use monitored deployment, backups, rate limiting, reverse-proxy HTTPS and secure secret management.

## Windows quick start — functional local learning environment

**Requirements:** Windows 10/11 x64, Python 3.11 or 3.12 x64 with `py` launcher, Internet access to install dependencies. Use a writable extracted directory such as `C:\Projects\PDF-Studio-Pro`.

1. Run **`scripts\setup_windows.bat`**. This creates `.venv`, installs dependencies, generates an **Ed25519 server key pair**, a **local-only administrator token**, and `config/license_client.json`, then runs the test suite. **Never share the `secrets/` folder.**
2. In a terminal, run **`scripts\start_local_license_server.bat`**. Keep this terminal open; local server listens on `127.0.0.1:8765`.
3. In a second terminal, run **`scripts\create_local_license.bat`**. Copy the printed `PSP-...` key; it is displayed only once. Creating another key will produce a different license.
4. Run **`scripts\run_windows.bat`**. Enter that key in the activation dialog. The app must reach the server to activate and verify. The next time it launches, no key entry is required, but server access remains mandatory.
5. Check PDF operations; for tests run **`scripts\test_windows.bat`**.

**For one-PC behavior:** Copy the same key to a second Windows PC (with the client config pointing to the same network-reachable server) and activate; it should be rejected with HTTP 409 until an administrator resets that key's device. `127.0.0.1` is *only for on-PC development*, not a remote multi-computer test.

### Admin operations

Run from project root while the server is available:

```powershell
.venv\Scripts\python.exe -m license_server.admin_cli create
.venv\Scripts\python.exe -m license_server.admin_cli list
.venv\Scripts\python.exe -m license_server.admin_cli reset-device --id 1
.venv\Scripts\python.exe -m license_server.admin_cli revoke --id 1
.venv\Scripts\python.exe -m license_server.admin_cli restore --id 1
.venv\Scripts\python.exe -m license_server.admin_cli audit --id 1
```

The local CLI reads `secrets/admin_token.txt` (server-only). For remote administration, specify `--url https://your-license-host` and set `PDFSP_ADMIN_TOKEN` securely or enter it at the prompt. Never place admin credentials inside the desktop executable. **Device reset only clears one active binding; it does not grant a new license.** Restore clears any existing device binding too.

### Developer server commands

```powershell
.venv\Scripts\python.exe -m license_server.cli init --base-url http://127.0.0.1:8765
.venv\Scripts\python.exe -m uvicorn license_server.api:app --host 127.0.0.1 --port 8765
```

`init` keeps an existing signing key and admin token; it rewrites the *public* client config for the requested URL. To serve on another machine, use HTTPS behind a reverse proxy; a **real externally reachable host** and correct DNS/TLS configuration are required. The source ZIP does **not** supply a live domain, cloud deployment, TLS certificate, or an online server.

## Building Windows EXE and installer

**Before public distribution:** deploy the license server at an HTTPS hostname, keep the server `secrets/` private and backed up, and run:

```powershell
.venv\Scripts\python.exe -m license_server.cli init --base-url https://licenses.example.com
.venv\Scripts\python.exe scripts\release_preflight.py
scripts\build_windows_portable.bat
scripts\build_windows_installer.bat
```

Replace `https://licenses.example.com` with your actual domain; it is **not** an available example service. The `init` command embeds only the *public* verification key into `config/license_client.json`. **Ensure the externally deployed server uses the same private key and database**.

- Portable (build on Windows): `dist\PDF-Studio-Pro\PDF-Studio-Pro.exe` plus all files in its directory. Copy the **whole directory**, not just the EXE.
- Installer (build on Windows with **Inno Setup 6**): `dist\installer\PDF-Studio-Pro-Setup-1.0.0.exe`.
- During local testing, you can override the release-preflight block for localhost only using `set PDFSP_ALLOW_LOCAL_BUILD=1` in the **same Command Prompt**, followed by `scripts\build_windows_portable.bat`. Such a build is **not production-usable** because it points to your own PC's loopback address.
- Neither script signs the EXE. Code-signing requires your own signing certificate and Windows SignTool integration.
- The source ZIP does not contain any installer or EXE and was not built or run on Windows in the authoring environment. Review `docs/WINDOWS_RELEASE_CHECKLIST.md`.

**PyInstaller documentation:** <https://pyinstaller.org/en/stable/usage.html>  
**Inno Setup documentation:** <https://jrsoftware.org/ishelp/>

## Data & security design

- Server private key: `secrets/license_private.pem`. Admin token: `secrets/admin_token.txt`. License DB: `secrets/licenses.sqlite3`. These are generated locally, never included in the source ZIP, and must be restricted to server admins.
- Public desktop config: `config/license_client.json` (generated by provisioning; intentionally absent from this ZIP). For public distribution it must point to a reachable HTTPS endpoint and retain the matching Ed25519 public key.
- Windows desktop activation state: `%LOCALAPPDATA%\PDFStudioPro\activation.json` (signed token only, **not the license key**).
- Hardware identity: Windows MachineGuid is read locally and hashed before transmission; no raw value is sent. Reinstalling Windows or cloning Windows images can change or duplicate this identifier; admin reset is the recovery path.
- Server verifies **current** revocation/generation state on each verification request; client additionally checks signatures locally. Any failure to connect at startup prevents the editor from opening.
- A failed periodic check closes the editor. **Unsaved changes could be lost** if server access is interrupted. This is an intentional strict online-only policy; adjust the grace strategy before commercial distribution if needed.
- **Do not** run the localhost Uvicorn configuration as an Internet-facing deployment, and do not deploy with the backend's debug/reload mode or without HTTPS, abuse protection and backups.

## Test suite

```powershell
.venv\Scripts\python.exe -m pytest -q
```

`tests/test_licensing.py` checks activation, startup checks, one-PC rejection under concurrent activation, Ed25519 tamper rejection, revoke/restore, device reset and admin authorization. Existing engine regression tests are preserved. The Qt GUI smoke test is skipped on platforms without PySide6 and has **not been validated on actual Windows** here. See `docs/TEST_RESULTS.txt` and `docs/WINDOWS_RELEASE_CHECKLIST.md`.

## Source tree

```text
app.py                              # Desktop launcher; online license gate
pdfstudio/ui.py                     # Part 1+2 editor and ribbon layout
pdfstudio/engine.py                 # PDF processing and AES-256
pdfstudio/dialogs.py                # PDF editing dialogs
pdfstudio/licensing.py              # Windows device identity, secure license client
pdfstudio/license_ui.py             # Qt activation dialog
license_server/api.py               # FastAPI endpoints; separate service
license_server/core.py              # Ed25519, SQLite transactions, license logic
license_server/cli.py              # Server-key provisioning
license_server/admin_cli.py        # Authenticated license administration
installer/PDFStudioPro.iss          # Inno Setup config
scripts/                            # Windows setup, server, test, build commands
config/license_client.example.json # Public config schema (not a working service)
assets/                             # App PNG and .ico
requirements*.txt                   # Desktop/server/build dependencies
tests/                              # PDF and license tests
docs/                               # UI reference, test logs, checklists
```

## Third-party license review

See `LICENSE-NOTE.txt`. **PyMuPDF uses AGPL or a commercial license**; choose a distribution model that complies. PySide6/Qt has LGPL/GPL/commercial conditions, including dynamic linking and applicable notice/redistribution duties. These obligations are **not** solved by an Inno Setup installer or paid license keys.
