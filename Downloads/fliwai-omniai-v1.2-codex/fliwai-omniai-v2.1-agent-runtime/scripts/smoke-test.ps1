param([string]$ApiBase = "http://localhost:8001")
$ErrorActionPreference = "Stop"
foreach ($path in @('/health/live','/health/ready','/health/deep')) {
  $url = "$ApiBase$path"
  Write-Host "Checking $url"
  $response = Invoke-RestMethod -Uri $url -Method Get
  if (-not $response.status) { throw "Unexpected response from $url" }
}
Write-Host "OmniAI smoke checks passed."
