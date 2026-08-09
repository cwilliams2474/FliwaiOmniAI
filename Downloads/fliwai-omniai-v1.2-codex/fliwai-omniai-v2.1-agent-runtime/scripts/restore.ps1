param([Parameter(Mandatory=$true)][string]$BackupDir, [switch]$ConfirmRestore)
$ErrorActionPreference = "Stop"
if (-not $ConfirmRestore) { throw "Restore is destructive. Re-run with -ConfirmRestore after confirming the target environment." }
& "$PSScriptRoot\verify-backup.ps1" -BackupDir $BackupDir
$manifest = Get-Content -Raw (Join-Path $BackupDir "manifest.json") | ConvertFrom-Json
$dbFile = Join-Path $BackupDir $manifest.database_file
$uploadsDir = Join-Path $BackupDir $manifest.uploads_directory
Write-Host "Restoring database..."
Get-Content -Raw $dbFile | docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
if ($LASTEXITCODE -ne 0) { throw "Database restore failed" }
Write-Host "Restoring uploads..."
docker compose exec -T backend sh -c 'rm -rf /app/uploads/*'
if ($LASTEXITCODE -ne 0) { throw "Could not clear upload directory" }
docker compose cp "$uploadsDir\." backend:/app/uploads/
if ($LASTEXITCODE -ne 0) { throw "Upload restore failed" }
docker compose restart backend
Write-Host "Restore complete. Verify /health/deep and application sign-in before declaring recovery complete."
