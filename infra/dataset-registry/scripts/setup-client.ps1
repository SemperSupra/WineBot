# ── Dataset Registry Client Setup (Windows PowerShell) ─────────────────────
# Run this on Windows to configure DVC + MinIO for the dataset registry.
#
# Usage:
#   .\scripts\setup-client.ps1
#   # Or with explicit credentials:
#   $env:INFRA_MINIO_ACCESS_KEY = "winebot-dvc"
#   $env:INFRA_MINIO_SECRET_KEY = "your-secret-key"
#   .\scripts\setup-client.ps1
# ──────────────────────────────────────────────────────────────────────────────

param(
    [string]$TruenasHost = $env:INFRA_TRUENAS_HOST,
    [int]$MinioPort = ($env:INFRA_MINIO_PORT -as [int]),
    [string]$Bucket = $env:INFRA_MINIO_BUCKET,
    [string]$AccessKey = $env:INFRA_MINIO_ACCESS_KEY,
    [string]$SecretKey = $env:INFRA_MINIO_SECRET_KEY
)

# Defaults
if (-not $TruenasHost) { $TruenasHost = "truenas.fritz.box" }
if (-not $MinioPort) { $MinioPort = 9000 }
if (-not $Bucket) { $Bucket = "winebot-models" }

$Endpoint = "http://${TruenasHost}:${MinioPort}"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $Here)

# ── Colors ───────────────────────────────────────────────────────────────────
$Host.UI.RawUI.ForegroundColor = "Green"
Write-Host "[INFO] Dataset Registry Client Setup (Windows)" -ForegroundColor Green
$Host.UI.RawUI.ForegroundColor = "Gray"

# ── Check Python ─────────────────────────────────────────────────────────────
Write-Host "[INFO] Checking Python..."
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Host "[ERROR] Python not found. Install Python 3.12+ from python.org" -ForegroundColor Red
    exit 1
}
Write-Host "[INFO] Python: $python"

# ── Check/Install DVC ───────────────────────────────────────────────────────
$dvc = (Get-Command dvc -ErrorAction SilentlyContinue).Source
if ($dvc) {
    $version = & dvc --version 2>$null
    Write-Host "[INFO] DVC already installed: $version" -ForegroundColor Green
} else {
    Write-Host "[INFO] Installing DVC with S3 support..."
    & python -m pip install dvc[s3] 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[INFO] DVC installed!" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] DVC installation failed" -ForegroundColor Red
        exit 1
    }
}

# ── Check if running in WineBot repo ─────────────────────────────────────────
$dvcConfig = Join-Path $ProjectRoot ".dvc" "config"
$inRepo = Test-Path $dvcConfig

if ($inRepo) {
    Set-Location $ProjectRoot
    Write-Host "[INFO] Found DVC repo at: $ProjectRoot"
} else {
    Write-Host "[WARN] No DVC repo found at $ProjectRoot" -ForegroundColor Yellow
    Write-Host "[WARN] Run 'dvc init' first, then run this script again." -ForegroundColor Yellow
}

# ── Configure Remote ─────────────────────────────────────────────────────────
if ($AccessKey -and $SecretKey) {
    Write-Host "[INFO] Configuring DVC remote 'truenas'..."

    if ($inRepo) {
        # Add or update remote
        & dvc remote add truenas "s3://${Bucket}" 2>$null | Out-Null
        & dvc remote modify truenas endpointurl "${Endpoint}" 2>$null
        & dvc remote modify truenas access_key_id "${AccessKey}" 2>$null
        & dvc remote modify truenas --local secret_access_key "${SecretKey}" 2>$null

        Write-Host "[INFO] DVC remote configured!" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Remote:    truenas"
        Write-Host "  Bucket:    ${Bucket}"
        Write-Host "  Endpoint:  ${Endpoint}"
        Write-Host ""

        # ── Test Connection ──────────────────────────────────────────────────
        Write-Host "[INFO] Testing connection..."
        $health = $null
        try {
            $health = Invoke-WebRequest -Uri "${Endpoint}/minio/health/live" -TimeoutSec 5 -UseBasicParsing
        } catch {
            $health = $null
        }

        if ($health -and $health.StatusCode -eq 200) {
            Write-Host "[INFO] MinIO reachable at ${Endpoint}" -ForegroundColor Green
            Write-Host ""
            Write-Host "Quick usage:"
            Write-Host "  dvc add models\your-data"
            Write-Host "  dvc push -r truenas"
            Write-Host ""
        } else {
            Write-Host "[WARN] Cannot reach MinIO at ${Endpoint}" -ForegroundColor Yellow
            Write-Host "  Verify TrueNAS is running and MinIO is deployed."
            Write-Host "  Test with: curl -v ${Endpoint}/minio/health/live"
        }
    }
} else {
    # ── Credential Instructions ───────────────────────────────────────────────
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║           DATASET REGISTRY — WINDOWS CLIENT SETUP            ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "No credentials found. Provide them via environment variables:"
    Write-Host ""
    Write-Host "  `$env:INFRA_TRUENAS_HOST = 'truenas.fritz.box'"
    Write-Host "  `$env:INFRA_MINIO_PORT = 9000"
    Write-Host "  `$env:INFRA_MINIO_BUCKET = 'winebot-models'"
    Write-Host "  `$env:INFRA_MINIO_ACCESS_KEY = 'winebot-dvc'"
    Write-Host "  `$env:INFRA_MINIO_SECRET_KEY = 'your-secret-key'"
    Write-Host "  .\scripts\setup-client.ps1"
    Write-Host ""

    # Create example env file
    $envExample = Join-Path $ProjectRoot ".env.registry.example"
    @"
# ── Dataset Registry Credentials ────────────────────────────────────────────
INFRA_TRUENAS_HOST=truenas.fritz.box
INFRA_MINIO_PORT=9000
INFRA_MINIO_BUCKET=winebot-models
INFRA_MINIO_ACCESS_KEY=winebot-dvc
INFRA_MINIO_SECRET_KEY=replace-with-actual-secret
"@ | Out-File -FilePath $envExample -Encoding utf8

    Write-Host "  Created: $envExample"
    Write-Host ""
}
