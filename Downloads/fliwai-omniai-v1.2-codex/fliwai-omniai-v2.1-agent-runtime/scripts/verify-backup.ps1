param([Parameter(Mandatory=$true)][string]$BackupDir)
$ErrorActionPreference = "Stop"
$manifestPath = Join-Path $BackupDir "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "manifest.json not found in $BackupDir" }
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
$dbPath = Join-Path $BackupDir $manifest.database_file
$uploadsDir = Join-Path $BackupDir $manifest.uploads_directory
if (-not (Test-Path $dbPath)) { throw "Database backup missing: $dbPath" }
if (-not (Test-Path $uploadsDir)) { throw "Uploads directory missing: $uploadsDir" }
if ((Get-FileHash -Algorithm SHA256 $dbPath).Hash -ne $manifest.database_sha256) { throw "Database checksum mismatch" }
if ((Get-Item $dbPath).Length -lt 100) { throw "Database backup is unexpectedly small" }
foreach ($item in $manifest.uploads) {
  $path = Join-Path $uploadsDir $item.path
  if (-not (Test-Path $path)) { throw "Upload backup missing: $($item.path)" }
  if ((Get-FileHash -Algorithm SHA256 $path).Hash -ne $item.sha256) { throw "Upload checksum mismatch: $($item.path)" }
}
Write-Host "Backup verification passed: $BackupDir"
