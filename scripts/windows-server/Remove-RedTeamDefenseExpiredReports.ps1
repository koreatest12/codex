#Requires -Version 5.1
# Lists expired generated reports by default. Removal requires -Apply and confirmation.
[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param(
    [ValidateRange(1,3650)][int]$RetentionDays = 90,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This tool supports Windows only.' }
. (Join-Path $PSScriptRoot 'RedTeamDefense-Storage.ps1')
$reports = Join-Path $env:ProgramData 'RedTeamDefense\Reports'
Test-RedTeamProtectedDirectory $reports -Recursive
$cutoff = (Get-Date).AddDays(-$RetentionDays)
$files = @(Get-ChildItem -LiteralPath $reports -File -Force | Where-Object {
    $_.Name -match '^RedTeamDefense-\d{8}-\d{6}\.(html|json|csv)$' -and $_.LastWriteTime -lt $cutoff
})
Write-Output ("Matching reports older than {0} days: {1}" -f $RetentionDays, $files.Count)
$files | Select-Object Name, Length, LastWriteTime
if (-not $Apply) { Write-Output 'PLAN only: no files removed.'; return }
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run as administrator.' }
foreach ($file in $files) {
    if ($PSCmdlet.ShouldProcess($file.FullName, 'Remove expired report')) {
        Remove-Item -LiteralPath $file.FullName -ErrorAction Stop
    }
}
