# Windows-friendly skills sync (same layout as sync-skills.sh).
# Usage: powershell -File scripts/sync-skills.ps1
$ErrorActionPreference = 'Stop'
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$CATEGORY = 'emaw'
$agents = @('coordinator','dev-frontend','dev-backend','reviewer','devops','qa')

function Sync-One([string]$src, [string]$agent) {
  $name = [IO.Path]::GetFileNameWithoutExtension($src)
  $destDir = Join-Path $ROOT "hermes-data\$agent\skills\$CATEGORY\$name"
  $dest = Join-Path $destDir 'SKILL.md'
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -Force $src $dest
  Write-Host "synced  $agent/$CATEGORY/$name"
}

foreach ($agent in $agents) {
  Get-ChildItem (Join-Path $ROOT 'skills\_shared\*.md') -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'README.md' } |
    ForEach-Object { Sync-One $_.FullName $agent }
  if ($agent -in @('dev-frontend','dev-backend')) {
    Get-ChildItem (Join-Path $ROOT 'skills\_dev-common\*.md') -ErrorAction SilentlyContinue |
      ForEach-Object { Sync-One $_.FullName $agent }
  }
  Get-ChildItem (Join-Path $ROOT "skills\$agent\*.md") -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'README.md' } |
    ForEach-Object { Sync-One $_.FullName $agent }
}
Write-Host 'skills in sync'
