# Memaix setup (Windows) — starta, öppna webbläsaren, klart.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kör i PowerShell:  .\setup.ps1
# Wizarden binder bara 127.0.0.1 — nås aldrig utifrån.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Port = if ($env:MEMAIX_SETUP_PORT) { $env:MEMAIX_SETUP_PORT } else { 8765 }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "X Docker Desktop kravs (enda beroendet): https://docs.docker.com/get-docker/"
    exit 1
}

$bytes = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$Token = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
$Url = "http://127.0.0.1:${Port}/?token=${Token}"

Write-Host ""
Write-Host "  Memaix setup startar ..."
Write-Host "  Oppna i din webblasare:  $Url"
Write-Host ""
Start-Process $Url

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & python scripts/setup_web.py --port $Port --token $Token
} else {
    docker run --rm -v "${PWD}:/repo" -w /repo -p "127.0.0.1:${Port}:${Port}" `
        python:3-alpine python scripts/setup_web.py --port $Port --token $Token --container
}

if (-not (Test-Path ".setup-result.json")) {
    Write-Host "X Ingen config skriven - avbrutet."
    exit 1
}
$result = Get-Content ".setup-result.json" | ConvertFrom-Json

if ($result.track -eq 1) {
    Write-Host ""
    Write-Host "  Trial-lage klart. Starta lokalt:  docker compose up -d"
    Write-Host "  Anslut Claude Desktop som stdio-MCP: se docs/AI-CLIENTS.md"
} else {
    Write-Host ""
    Write-Host "  Reser stacken ..."
    $profiles = @("--profile", "hydra")
    if ($result.tunnel_provider -eq "cloudflare") { $profiles += @("--profile", "tunnel") }
    docker compose @profiles up -d
    Write-Host "  Kor halsokontroll ..."
    if ($python) {
        & python scripts/bootstrap.py --doctor
    } else {
        docker run --rm --network host -v "${PWD}:/repo" -w /repo `
            python:3-alpine sh -c "pip -q install pyyaml && python scripts/bootstrap.py --doctor"
    }
}
Write-Host ""
Write-Host "  Klart! Nasta steg: docs/AI-CLIENTS.md (koppla din AI)."
