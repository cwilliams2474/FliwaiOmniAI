param([string]$OutputDir = ".\backups")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$bundle = Join-Path $OutputDir "omniai-backup-$stamp"
$uploadsDir = Join-Path $bundle "uploads"
New-Item -ItemType Directory -Force -Path $uploadsDir | Out-Null
$dbFile = Join-Path $bundle "database.sql"
$manifestFile = Join-Path $bundle "manifest.json"

Write-Host "Backing up PostgreSQL..."
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | Out-File -FilePath $dbFile -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }

Write-Host "Backing up uploaded files..."
docker compose cp backend:/app/uploads/. $uploadsDir
if ($LASTEXITCODE -ne 0) { throw "Upload backup failed" }

$dbHash = (Get-FileHash -Algorithm SHA256 $dbFile).Hash
$uploadInventory = Get-ChildItem -File -Recurse $uploadsDir | Sort-Object FullName | ForEach-Object {
  [ordered]@{ path = $_.FullName.Substring($uploadsDir.Length).TrimStart('\','/'); sha256 = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash; bytes = $_.Length }
}
$manifest = [ordered]@{
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  database_file = "database.sql"
  database_sha256 = $dbHash
  uploads_directory = "uploads"
  uploads = @($uploadInventory)
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $manifestFile
Write-Host "Backup complete: $bundle"
Write-Host "Run .\scripts\verify-backup.ps1 -BackupDir `"$bundle`" before moving it off-host."
