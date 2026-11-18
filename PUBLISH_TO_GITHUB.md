# Upload PDF Studio Pro v1.0 Release Preview to the EXISTING GitHub repository

The target repository **already exists**:

**https://github.com/IRFANSK-him/PDF-Studio-Pro-v1.0-release-preview**

This ZIP contains **the entire cumulative Parts 1–3 source project**, not just a README and not a prebuilt Windows installer.

## Windows: easiest upload method

1. Extract the **complete ZIP** to a new folder. Do not extract only one file.
2. Double-click **`PUBLISH_TO_GITHUB.bat`** at the top level of the extracted folder.
3. If Git for Windows is missing, install it from https://git-scm.com/download/win and double-click the script again.
4. When Git Credential Manager prompts, sign in to GitHub as **IRFANSK-him**. The script does not request or store a GitHub password or personal access token itself.

The script adds the full source tree to the existing repository `main` branch. It accounts for the GitHub-created initial `README.md` commit and does **not** force push or discard newer, unrelated work. The GitHub Actions verification workflow runs automatically on the pushed source.

## Alternative: command line

With Git for Windows installed, open Git Bash or PowerShell from this extracted folder and execute the provided `publish_to_github.ps1` script with PowerShell. Do not paste licensing private keys or tokens into GitHub.

## Files included

- `app.py`, `pdfstudio/`: PySide6 application and PDF engine (Parts 1 + 2)
- `license_server/`, `config/license_client.example.json`: local development license system (Part 3)
- `assets/`, `docs/`, `tests/`: UI reference, documentation, automated tests
- `.github/workflows/`: repository test automation and optional Windows portable/installer preview builds
- `scripts/`, `installer/`: Windows run, tests, portable EXE and installer build configuration
- `.gitignore`: prevents accidental upload of local license secrets, activation state and generated binaries

## Scope of this package

This is a **release-preview source candidate**. Automated backend tests passed in the authoring environment (33 passed, 1 GUI smoke test skipped). The UI, Windows executable and installer are not yet fully verified; the licensing server must be configured separately before public distribution. Follow the release checklist in `docs/WINDOWS_RELEASE_CHECKLIST.md`.
