$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$target = Join-Path $repoRoot 'vendor/subdue'
if (-not (Test-Path -LiteralPath (Join-Path $target 'src/Subdue.py'))) {
    git clone https://github.com/holderlb/Subdue.git $target
    if ($LASTEXITCODE -ne 0) { throw 'SUBDUE download failed' }
}
if (-not (Test-Path -LiteralPath (Join-Path $target '.git'))) {
    Write-Output 'Using the supplied vendor source snapshot; revision is recorded in vendor/subdue.lock.json.'
    exit 0
}
git -C $target checkout f33567dea2fa7e9595c27b807f16b120a7bdebb2
if ($LASTEXITCODE -ne 0) { throw 'SUBDUE revision selection failed' }
