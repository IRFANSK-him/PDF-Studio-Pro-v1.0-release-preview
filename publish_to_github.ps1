# PDF Studio Pro v1.0 Release Preview - upload this extracted project to its GitHub repository.
# Requirements: Git for Windows, GitHub authentication through Git Credential Manager.
# Safety: does not force push; refuses to overwrite a repository with unrelated project files.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/IRFANSK-him/PDF-Studio-Pro-v1.0-release-preview.git'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project

function Run-Git {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw ('Git command failed: git ' + ($Arguments -join ' '))
    }
}

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git for Windows is not installed. Install https://git-scm.com/download/win and run PUBLISH_TO_GITHUB.bat again.'
    }
    if (-not (Test-Path -LiteralPath '.git')) {
        Run-Git -Arguments @('init', '-b', 'main')
    }
    $branch = (& git branch --show-current).Trim()
    if ($branch -and $branch -ne 'main') {
        throw ('This folder is currently on branch ' + $branch + '. Refusing to push unexpected branch.')
    }
    $remotes = @(& git remote)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Git remotes.' }
    if ('origin' -notin $remotes) {
        Run-Git -Arguments @('remote', 'add', 'origin', $repo)
    } else {
        $origin = (& git remote get-url origin).Trim()
        if ($LASTEXITCODE -ne 0 -or $origin -ne $repo) {
            throw ('The origin remote differs from the expected repository: ' + $origin)
        }
    }

    Write-Host 'Checking the target GitHub repository...' -ForegroundColor Cyan
    Run-Git -Arguments @('fetch', 'origin', 'main')
    $remoteFiles = @(& git ls-tree -r --name-only 'origin/main')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect remote main branch.' }
    # The initial GitHub repository contained only a README.md. A new repository may be empty.
    # If this script was run before, a related commit history is safe to fast-forward.
    Run-Git -Arguments @('add', '--all')
    $staged = & git diff --cached --name-only
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect staged files.' }
    if ($staged) {
        $author = (& git config user.name)
        $authorEmail = (& git config user.email)
        if (-not $author) { Run-Git -Arguments @('config', 'user.name', 'IRFANSK-him') }
        if (-not $authorEmail) { Run-Git -Arguments @('config', 'user.email', '145809848+IRFANSK-him@users.noreply.github.com') }
        Run-Git -Arguments @('commit', '-m', 'Upload complete PDF Studio Pro v1.0 release preview source')
    }
    # Exit status 0 means the remote commit is already an ancestor of our local HEAD.
    # Exit status 1 means it is not; no stderr or exceptions are expected in normal Git.
    & git merge-base --is-ancestor origin/main HEAD
    $remoteIsAncestor = ($LASTEXITCODE -eq 0)
    if (-not $remoteIsAncestor -and ($remoteFiles.Count -ne 1 -or $remoteFiles[0] -ne 'README.md')) {
        throw 'The target repository has changed beyond its initial README. No files were pushed.'
    }
    if (-not $remoteIsAncestor) {
        # Keep the GitHub-created README commit as an ancestor while retaining the complete local project tree.
        Run-Git -Arguments @('merge', '--allow-unrelated-histories', '-s', 'ours', '-m', 'Integrate initial GitHub README commit', 'origin/main')
    }
    Write-Host 'Publishing complete project source...' -ForegroundColor Cyan
    Run-Git -Arguments @('push', '-u', 'origin', 'main')
    Write-Host ''
    Write-Host 'SUCCESS: The project source is published to:' -ForegroundColor Green
    Write-Host 'https://github.com/IRFANSK-him/PDF-Studio-Pro-v1.0-release-preview'
    Write-Host 'The Verify preview source workflow will start automatically.'
} catch {
    Write-Host ''
    Write-Host ('PUBLISH FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'No force-push was attempted. Check that Git is installed and authenticated with your GitHub account.'
    exit 1
}
