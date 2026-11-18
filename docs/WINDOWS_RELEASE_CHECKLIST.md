# Part 3 Windows acceptance / release checklist

Every box below is **unverified until tested on a real Windows 10/11 x64 PC**.

- [ ] Complete `scripts/setup_windows.bat`, including PySide6, PDF engine and tests.
- [ ] Start local server, generate license, activate editor, open multiple PDFs.
- [ ] Confirm original UI layout, tabs, thumbnails, zoom, search, keyboard shortcuts.
- [ ] Save, reorder, crop and convert PDFs; reopen results.
- [ ] Highlight, insert text/image, watermark, metadata, compression, real redaction.
- [ ] Encrypt PDF with AES-256 and verify using an independent PDF reader.
- [ ] Restart with local server running: app opens with signed cached activation token.
- [ ] Restart with server unavailable: app must refuse to open.
- [ ] Try activating the same license on a different Windows PC: must be blocked.
- [ ] Reset the license binding on server: old device invalid; new device can activate.
- [ ] Revoke license: previously activated device fails verification.
- [ ] Restore license: previously signed token remains invalid until reactivation.
- [ ] Leave editor running for 10+ minutes; check online verification interval.
- [ ] Run `scripts/build_windows_portable.bat`; validate copy of complete folder on a clean PC.
- [ ] Run `scripts/build_windows_installer.bat` with Inno Setup 6; test install, launch, update and uninstall.
- [ ] Confirm installed EXE can locate the signed-public-key client configuration.
- [ ] Confirm no secret private key, admin token, or license DB is bundled with installer.
- [ ] For public release, use real domain and valid HTTPS, backups and rate limiting.
- [ ] Review AGPL/commercial PyMuPDF and Qt/PySide6 license obligations.
- [ ] Code-sign executable and installer if distributing publicly.
- [ ] Validate on a freshly installed Windows user account, standard permissions and antivirus.

**Release decision:** No production-release claim until Windows GUI, installer, security configuration and licensing tests are passed. Source can be evaluated beforehand.
