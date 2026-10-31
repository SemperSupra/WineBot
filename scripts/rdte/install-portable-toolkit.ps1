#requires -Version 5.1
param(
  [Parameter(Mandatory=$true)][ValidateSet('Install','Uninstall')][string]$Operation,
  [Parameter(Mandatory=$true)][string]$PackageDir,
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [string]$Version = 'rdte-v0'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Assert-SafeName([string]$s) {
  if ($s -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' -or $s -eq '.' -or $s -eq '..') { throw 'unsafe_version' }
}
function Assert-NoReparsePath([string]$path) {
  $current = [IO.Path]::GetFullPath($path)
  while ($true) {
    if (Test-Path -LiteralPath $current) {
      $item = Get-Item -LiteralPath $current -Force
      if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'reparse_path_refused' }
    }
    $parent = [IO.Path]::GetDirectoryName($current)
    if ([string]::IsNullOrEmpty($parent) -or $parent -eq $current) { break }
    $current = $parent
  }
}
Assert-SafeName $Version
Assert-NoReparsePath $InstallRoot
Assert-NoReparsePath $PackageDir
$root = [IO.Path]::GetFullPath($InstallRoot)
$destination = Join-Path $root $Version
if ($Operation -eq 'Uninstall') {
  Assert-NoReparsePath $destination
  if (-not (Test-Path -LiteralPath $destination -PathType Container)) { return }
  $marker = Join-Path $destination 'manifest.json'
  if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'refuse_unowned_uninstall' }
  Assert-NoReparsePath $marker
  $installed = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
  if ($installed.schema -ne 'winebot.toolkit.package.v0' -or $installed.status -ne 'synthetic-rdte-only') { throw 'refuse_unowned_uninstall' }
  foreach ($name in @('bin/win_event_observer.exe','bin/win_event_fixture.exe','manifest.json')) {
    $file = Join-Path $destination ($name.Replace('/',[IO.Path]::DirectorySeparatorChar))
    if (Test-Path -LiteralPath $file -PathType Leaf) { Remove-Item -LiteralPath $file -Force }
  }
  $bin = Join-Path $destination 'bin'
  if (Test-Path -LiteralPath $bin) { if (@(Get-ChildItem -LiteralPath $bin -Force).Count -eq 0) { Remove-Item -LiteralPath $bin } }
  if (@(Get-ChildItem -LiteralPath $destination -Force).Count -eq 0) { Remove-Item -LiteralPath $destination }
  Write-Output 'PASS: manifest-owned files removed'
  return
}
if (Test-Path -LiteralPath $destination) { throw 'destination_exists_no_overwrite' }
$package = [IO.Path]::GetFullPath($PackageDir)
$manifestFile = Join-Path $package 'manifest.json'
$manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'winebot.toolkit.package.v0' -or $manifest.status -ne 'synthetic-rdte-only' -or $manifest.target -notin @('win-x64','win-x86')) { throw 'invalid_manifest' }
$names = @('bin/win_event_observer.exe','bin/win_event_fixture.exe')
if (@($manifest.files.PSObject.Properties).Count -ne 2) { throw 'invalid_manifest_files' }
foreach ($name in $names) {
  $expected = $manifest.files.PSObject.Properties[$name].Value
  if ($expected -notmatch '^[a-f0-9]{64}$') { throw 'invalid_digest' }
  $source = Join-Path $package ($name.Replace('/',[IO.Path]::DirectorySeparatorChar))
  Assert-NoReparsePath $source
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'missing_file' }
  if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) { throw 'hash_mismatch' }
}
New-Item -ItemType Directory -Path $root -Force | Out-Null
$staging = Join-Path $root ('.staging-' + [guid]::NewGuid().ToString('N'))
try {
  New-Item -ItemType Directory -Path (Join-Path $staging 'bin') -Force | Out-Null
  foreach ($name in $names) {
    Copy-Item -LiteralPath (Join-Path $package ($name.Replace('/',[IO.Path]::DirectorySeparatorChar))) -Destination (Join-Path $staging ($name.Replace('/',[IO.Path]::DirectorySeparatorChar)))
  }
  Copy-Item -LiteralPath $manifestFile -Destination (Join-Path $staging 'manifest.json')
  foreach ($name in $names) {
    $digest = (Get-FileHash -LiteralPath (Join-Path $staging ($name.Replace('/',[IO.Path]::DirectorySeparatorChar))) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -cne $manifest.files.PSObject.Properties[$name].Value) { throw 'staged_hash_mismatch' }
  }
  Assert-NoReparsePath $root
  if (Test-Path -LiteralPath $destination) { throw 'destination_exists_no_overwrite' }
  Move-Item -LiteralPath $staging -Destination $destination
  Write-Output 'PASS: staged and verified per-user install'
} finally {
  if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
