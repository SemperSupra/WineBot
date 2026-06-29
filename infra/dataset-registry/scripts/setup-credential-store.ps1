<#
.SYNOPSIS
    Dataset Registry — Windows Credential Manager Integration

.DESCRIPTION
    Stores and retrieves DVC/Garage S3 credentials in the Windows Credential Manager.
    Uses the CredentialManager PowerShell module for secure storage.

.PARAMETER AccessKey
    S3 access key ID to store (e.g., GK... from Garage)

.PARAMETER SecretKey
    S3 secret access key to store

.PARAMETER Host
    S3 endpoint hostname (default: truenas.fritz.box)

.PARAMETER Port
    S3 endpoint port (default: 30188)

.PARAMETER Export
    Print credentials as environment variables

.PARAMETER Status
    Show whether credentials are stored

.PARAMETER ShowFormat
    Show the Windows Credential Manager format help

.EXAMPLE
    # Store credentials
    .\scripts\setup-credential-store.ps1 -AccessKey "GKxxxx" -SecretKey "s3cr3t"

    # Export for use in other scripts
    .\scripts\setup-credential-store.ps1 -Export

    # Check status
    .\scripts\setup-credential-store.ps1 -Status

    # Show credential format reference
    .\scripts\setup-credential-store.ps1 -ShowFormat
#>

param(
    [string]$AccessKey = "",
    [string]$SecretKey = "",
    [string]$Hostname = "",
    [int]$Port = 0,
    [switch]$Export,
    [switch]$Status,
    [switch]$ShowFormat
)

# ── Credential Target Names ───────────────────────────────────────────────────
# Windows Credential Manager stores by target name (like a key).
$TARGET_ACCESS_KEY = "WineBotDatasetRegistry/AccessKey"
$TARGET_SECRET_KEY = "WineBotDatasetRegistry/SecretKey"
$TARGET_HOST = "WineBotDatasetRegistry/Host"
$TARGET_PORT = "WineBotDatasetRegistry/Port"

# ── Help: Show credential format reference ───────────────────────────────────
if ($ShowFormat) {
    Write-Host "╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║   Windows Credential Manager — Dataset Registry Format           ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Credentials are stored as Windows Generic Credentials with these"
    Write-Host "target names in the Windows Credential Manager:"
    Write-Host ""
    Write-Host "  Target Name                          │ Content"
    Write-Host "  ─────────────────────────────────────┼─────────────────────"
    Write-Host "  WineBotDatasetRegistry/AccessKey     │ S3 Access Key ID"
    Write-Host "  WineBotDatasetRegistry/SecretKey     │ S3 Secret Access Key"
    Write-Host "  WineBotDatasetRegistry/Host          │ S3 endpoint hostname"
    Write-Host "  WineBotDatasetRegistry/Port          │ S3 endpoint port"
    Write-Host ""
    Write-Host "To view/edit manually:"
    Write-Host "  1. Open Control Panel → User Accounts → Credential Manager"
    Write-Host "  2. Click 'Windows Credentials'"
    Write-Host "  3. Look under 'Generic Credentials'"
    Write-Host ""
    Write-Host "Or automate with this script:"
    Write-Host "  PS> .\scripts\setup-credential-store.ps1 -AccessKey 'GK...' -SecretKey '...'"
    Write-Host "  PS> .\scripts\setup-credential-store.ps1 -Export"
    Write-Host "  PS> .\scripts\setup-credential-store.ps1 -Status"
    Write-Host ""
    Write-Host "In CI/CD pipelines, use environment variables instead:"
    Write-Host "  `$env:INFRA_MINIO_ACCESS_KEY = 'GK...'"
    Write-Host "  `$env:INFRA_MINIO_SECRET_KEY = '...'"
    Write-Host "  `$env:INFRA_MINIO_PORT = 30188"
    Write-Host ""
    return
}

# ── Helper: Check if CredentialManager module is available ───────────────────
function Test-CredentialManagerModule {
    try {
        $null = Get-Module -ListAvailable -Name CredentialManager
        return $true
    } catch {
        return $false
    }
}

# ── Helper: Install CredentialManager module ─────────────────────────────────
function Install-CredentialManagerModule {
    Write-Host "[INFO] Installing CredentialManager PowerShell module..." -ForegroundColor Yellow
    try {
        Install-Module -Name CredentialManager -Force -Scope CurrentUser -AllowClobber -ErrorAction Stop
        Write-Host "[INFO] CredentialManager module installed." -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[ERROR] Could not install CredentialManager module." -ForegroundColor Red
        Write-Host "  Try: Install-Module -Name CredentialManager -Force -Scope CurrentUser" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Prerequisites:"
        Write-Host "    PowerShellGet: Install-Module -Name PowerShellGet -Force -Scope CurrentUser" -ForegroundColor Gray
        Write-Host "    Execution Policy: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned" -ForegroundColor Gray
        return $false
    }
}

# ── Helper: Store credential ─────────────────────────────────────────────────
function Set-CredentialStore($Target, $Username, $Password) {
    try {
        if (-not (Get-Module -Name CredentialManager)) {
            Import-Module CredentialManager -ErrorAction Stop
        }
        $cred = New-Object System.Management.Automation.PSCredential($Username, (ConvertTo-SecureString $Password -AsPlainText -Force))
        Set-VaultCredential -Target $Target -Credentials $cred -ErrorAction Stop | Out-Null
        return $true
    } catch {
        # Fallback: use cmdkey.exe (built-in Windows)
        try {
            & cmdkey.exe /generic:$Target /user:$Username /pass:$Password 2>&1 | Out-Null
            return $true
        } catch {
            return $false
        }
    }
}

# ── Helper: Get credential ───────────────────────────────────────────────────
function Get-CredentialStore($Target) {
    try {
        if (-not (Get-Module -Name CredentialManager)) {
            Import-Module CredentialManager -ErrorAction Stop
        }
        $cred = Get-VaultCredential -Target $Target -ErrorAction Stop
        if ($cred) {
            $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password)
            return [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
        }
    } catch {
        # Fallback: check cmdkey stored creds via a custom search
    }
    return $null
}

# ── Helper: Test if credential exists ────────────────────────────────────────
function Test-CredentialExists($Target) {
    $val = Get-CredentialStore $Target
    return (-not [string]::IsNullOrEmpty($val))
}

# ── Defaults ──────────────────────────────────────────────────────────────────
$Defaults = @{
    Hostname = "truenas.fritz.box"
    Port = 30188
}

# ── Mode: Status ─────────────────────────────────────────────────────────────
if ($Status) {
    Write-Host "╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║   Dataset Registry — Windows Credential Manager Status          ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    $hasModule = Test-CredentialManagerModule
    Write-Host "CredentialManager module: $($hasModule ? '✓ available' : '✗ not installed')"

    $ak = Get-CredentialStore $TARGET_ACCESS_KEY
    $sk = Get-CredentialStore $TARGET_SECRET_KEY
    $hostVal = Get-CredentialStore $TARGET_HOST
    $portVal = Get-CredentialStore $TARGET_PORT

    Write-Host "Access Key:  $($ak ? '✓ stored' : '✗ missing')"
    Write-Host "Secret Key:  $($sk ? '✓ stored' : '✗ missing')"
    Write-Host "Host:        $(if ($hostVal) { $hostVal } else { 'truenas.fritz.box (default)' })"
    Write-Host "Port:        $(if ($portVal) { $portVal } else { '30188 (default)' })"

    if ($ak -and $sk) {
        Write-Host ""
        Write-Host "Credentials present. To export:" -ForegroundColor Green
        Write-Host "  .\scripts\setup-credential-store.ps1 -Export" -ForegroundColor Gray
    } else {
        Write-Host ""
        Write-Host "Credentials missing. To store:" -ForegroundColor Yellow
        Write-Host "  .\scripts\setup-credential-store.ps1 -AccessKey 'GK...' -SecretKey '...'" -ForegroundColor Gray
    }
    return
}

# ── Mode: Export ─────────────────────────────────────────────────────────────
if ($Export) {
    $ak = Get-CredentialStore $TARGET_ACCESS_KEY
    $sk = Get-CredentialStore $TARGET_SECRET_KEY
    $hostVal = Get-CredentialStore $TARGET_HOST
    $portVal = Get-CredentialStore $TARGET_PORT

    if ([string]::IsNullOrEmpty($ak) -or [string]::IsNullOrEmpty($sk)) {
        Write-Host "[ERROR] Credentials not found in Windows Credential Manager." -ForegroundColor Red
        Write-Host "  Store them first:" -ForegroundColor Yellow
        Write-Host "    .\scripts\setup-credential-store.ps1 -AccessKey 'GK...' -SecretKey '...'" -ForegroundColor Gray
        exit 1
    }

    # Output env vars for eval in PowerShell
    Write-Host "`$env:INFRA_MINIO_ACCESS_KEY = '$ak'"
    Write-Host "`$env:INFRA_MINIO_SECRET_KEY = '$sk'"
    if ($hostVal) { Write-Host "`$env:INFRA_TRUENAS_HOST = '$hostVal'" }
    if ($portVal) { Write-Host "`$env:INFRA_MINIO_PORT = $hostVal" }

    return
}

# ── Mode: Store ──────────────────────────────────────────────────────────────
if ([string]::IsNullOrEmpty($AccessKey) -or [string]::IsNullOrEmpty($SecretKey)) {
    Write-Host "[ERROR] -AccessKey and -SecretKey are required for storage." -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\scripts\setup-credential-store.ps1 -AccessKey 'GK...' -SecretKey '...'"
    Write-Host "  .\scripts\setup-credential-store.ps1 -Export"
    Write-Host "  .\scripts\setup-credential-store.ps1 -Status"
    Write-Host "  .\scripts\setup-credential-store.ps1 -ShowFormat"
    exit 1
}

# Default host/port
if ([string]::IsNullOrEmpty($Hostname)) { $Hostname = $Defaults.Hostname }
if ($Port -eq 0) { $Port = $Defaults.Port }

# Ensure CredentialManager module
$hasModule = Test-CredentialManagerModule
if (-not $hasModule) {
    $installed = Install-CredentialManagerModule
    if (-not $installed) {
        # Fall back to cmdkey
        Write-Host "[INFO] Falling back to cmdkey.exe (built-in credential storage)..." -ForegroundColor Yellow
    }
}

Write-Host "[INFO] Storing credentials in Windows Credential Manager..." -ForegroundColor Green

$akOk = Set-CredentialStore -Target $TARGET_ACCESS_KEY -Username "AccessKey" -Password $AccessKey
$skOk = Set-CredentialStore -Target $TARGET_SECRET_KEY -Username "SecretKey" -Password $SecretKey
$hostOk = Set-CredentialStore -Target $TARGET_HOST -Username "Host" -Password $Hostname
$portOk = Set-CredentialStore -Target $TARGET_PORT -Username "Port" -Password $Port.ToString()

if ($akOk -and $skOk) {
    Write-Host "[INFO] Credentials stored successfully." -ForegroundColor Green
    Write-Host ""
    Write-Host "  To view in Credential Manager:" -ForegroundColor Gray
    Write-Host "    Control Panel → User Accounts → Credential Manager" -ForegroundColor Gray
    Write-Host "    → Windows Credentials → Generic Credentials" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  To export to env vars:" -ForegroundColor Gray
    Write-Host "    .\scripts\setup-credential-store.ps1 -Export" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  To run client setup (after export):" -ForegroundColor Gray
    Write-Host "    .\scripts\setup-client.ps1" -ForegroundColor Gray
} else {
    Write-Host "[WARN] Some credentials may not have stored correctly." -ForegroundColor Yellow
    Write-Host "  Check with: .\scripts\setup-credential-store.ps1 -Status" -ForegroundColor Yellow
}
