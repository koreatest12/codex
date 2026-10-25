#Requires -Version 5.1
<#
.SYNOPSIS
Read-only Windows Server readiness checks for hosting the Linux WAS in Hyper-V.
This script never installs Docker Desktop, changes firewall rules or creates a VM.
#>
[CmdletBinding()]
param([switch]$RequireHyperV)

$ErrorActionPreference = 'Stop'
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$server = [int]$os.ProductType -ne 1
Write-Output ("OS: {0} (build {1})" -f $os.Caption, $os.BuildNumber)
Write-Output ("Windows Server: {0}" -f $server)
if (-not $server) {
    Write-Warning 'This guide targets Windows Server. Client Windows has different Docker requirements.'
}
$role = Get-Command -Name Get-WindowsFeature -ErrorAction SilentlyContinue
$installed = $false
if ($role) {
    $feature = Get-WindowsFeature -Name Hyper-V -ErrorAction SilentlyContinue
    $installed = $null -ne $feature -and $feature.Installed
}
Write-Output ("Hyper-V role installed: {0}" -f $installed)
if (-not $installed) {
    Write-Warning 'Enable Hyper-V after reviewing host requirements, then reboot. No changes were made.'
}
$client = Get-Command -Name ssh.exe -ErrorAction SilentlyContinue
Write-Output ("OpenSSH client available: {0}" -f ($null -ne $client))
Write-Output 'Docker Desktop on Windows Server is unsupported. Use Ubuntu Server in Hyper-V for Linux containers.'
Write-Output 'This is host-readiness information, not proof that the WAS is running.'
if ($RequireHyperV -and -not $installed) { exit 2 }
