# PDF Studio Pro v1.0 — Release Preview

**Cumulative Windows PDF editor source project: Parts 1 + 2 + 3.**

This repository contains the PySide6 PDF editing desktop application, page management and conversion tools, a development online licensing server, test cases, Windows setup/build scripts, and Inno Setup installer configuration. The user-supplied UI reference is included in `docs/approved-ui-reference.jpg`.

> **Release preview — not a verified production executable.** An HTTPS licensing endpoint and a Windows acceptance test are required before distributing a final app. No activation keys or server private keys are shipped.

## Publishing this project to GitHub

This project was packaged specifically for the existing repository [IRFANSK-him/PDF-Studio-Pro-v1.0-release-preview](https://github.com/IRFANSK-him/PDF-Studio-Pro-v1.0-release-preview). **After extracting the ZIP on Windows, double-click `PUBLISH_TO_GITHUB.bat`** to upload all source files with Git. The script safely merges the initial GitHub README commit, does not force-push, and stops if it detects an unexpected remote state. See [`PUBLISH_TO_GITHUB.md`](PUBLISH_TO_GITHUB.md).

## Included modules

| Stage | Capabilities |
|---|---|
| Part 1 | PDF viewing, navigation, search, page thumbnails, drag-and-drop reorder, crop, PDF-to-PNG, images-to-PDF, shortcuts, page-order undo/redo |
| Part 2 | Text/image insertion, highlight, permanent redaction, watermark, metadata, compression, password protection, AES-256 |
| Part 3 | Online lifetime licensing, one-PC binding, activation, revocation, reset, license admin, build scripts and installer configuration |

## Running from source on Windows

With Python 3.11/3.12 (64-bit) installed:

1. Run `scripts\setup_windows.bat`.
2. Start the local development server with `scripts\start_local_license_server.bat`.
3. Run `scripts\create_local_license.bat` in another terminal and retain the test key.
4. Run `scripts\run_windows.bat` to open the application and activate the key.

Run automated tests with `scripts\test_windows.bat`. Build the portable application with `scripts\build_windows_portable.bat` (developer-only local builds need `PDFSP_ALLOW_LOCAL_BUILD=1`); build an installer with `scripts\build_windows_installer.bat` after installing Inno Setup 6.

For full documentation see [`docs/ORIGINAL_PART3_README.md`](docs/ORIGINAL_PART3_README.md), [`docs/WINDOWS_RELEASE_CHECKLIST.md`](docs/WINDOWS_RELEASE_CHECKLIST.md), and [`docs/PDF_EDITOR_NOTES.md`](docs/PDF_EDITOR_NOTES.md).

## GitHub Windows EXE build

After the code is published, `.github/workflows/verify-source.yml` runs tests on every push. The separate **Build Windows release preview** workflow is manual and creates EXE/installer artifacts only when you set the `PDFSP_LICENSE_SERVER_URL` and `PDFSP_LICENSE_SERVER_PUBLIC_KEY_PEM` repository Actions secrets. These are the *public* endpoint and verification key, not the server's private key. Without a deployed HTTPS service, the build is intentionally blocked rather than producing a non-activatable public EXE.

## Security and licensing

Never commit or publish `secrets/`, private signing keys, admin credentials, local SQLite databases, personal activation state, or the generated `config/license_client.json`. These are excluded from Git by `.gitignore`. PyMuPDF is AGPL/commercial dual-licensed; review [`LICENSE-NOTE.txt`](LICENSE-NOTE.txt) before redistribution.

**Testing as packaged:** 33 automated tests passed, 1 Windows GUI smoke test skipped in the authoring environment. This is not a claim that the full Windows GUI and installer have passed acceptance testing.
