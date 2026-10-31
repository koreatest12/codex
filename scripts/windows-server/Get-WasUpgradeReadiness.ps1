#Requires -Version 5.1
<#
.SYNOPSIS
Read-only Windows Server OS and Hyper-V WAS upgrade readiness inventory.
.DESCRIPTION
Does NOT install Windows Updates, upgrade the OS, reboot, create a VM,
modify firewall rules, change services or access Ubuntu guest secrets.
No hostnames, IP addresses, tokens, user profiles or VM names are emitted.
Run in an elevated PowerShell for best role/cluster visibility.
#>
[CmdletBinding()]
param(
    [switch]$AsJson,
    [switch]$RequireServer
)
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$computer = Get-CimInstance -ClassName Win32_ComputerSystem
$isServer = [int]$os.ProductType -ne 1
$osDrive = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $env:SystemDrive) -ErrorAction SilentlyContinue

function Get-FeatureInstalled([string]$name) {
    if (-not (Get-Command Get-WindowsFeature -ErrorAction SilentlyContinue)) { return $null }
    try {
        $feature = Get-WindowsFeature -Name $name -ErrorAction Stop
        return [bool]$feature.Installed
    } catch { return $null }
}
$hyperv = Get-FeatureInstalled 'Hyper-V'
$cluster = Get-FeatureInstalled 'Failover-Clustering'
$pendingReboot = $false
$pendingKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
)
foreach ($key in $pendingKeys) {
    if (Test-Path -LiteralPath $key) { $pendingReboot = $true }
}
try {
    $rename = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name PendingFileRenameOperations -ErrorAction Stop
    if ($null -ne $rename.PendingFileRenameOperations) { $pendingReboot = $true }
} catch { }

$vmCount = $null
$activeVMs = $null
$checkpointCount = $null
if ($hyperv -eq $true -and (Get-Command Get-VM -ErrorAction SilentlyContinue)) {
    try {
        $vms = @(Get-VM -ErrorAction Stop)
        $vmCount = $vms.Count
        $activeVMs = @($vms | Where-Object { $_.State -eq 'Running' }).Count
        if (Get-Command Get-VMSnapshot -ErrorAction SilentlyContinue) {
            $snapshots = @(foreach ($vm in $vms) {
                Get-VMSnapshot -VM $vm -ErrorAction SilentlyContinue
            })
            $checkpointCount = $snapshots.Count
        }
    } catch {
        Write-Verbose 'VM inventory unavailable with current permissions.'
    }
}

$result = [ordered]@{
    collected_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    windows_server = $isServer
    os_caption = [string]$os.Caption
    os_version = [string]$os.Version
    build_number = [string]$os.BuildNumber
    installation_type = [string]$os.OSArchitecture
    system_memory_gib = [math]::Round([double]$computer.TotalPhysicalMemory / 1GB, 1)
    system_disk_free_gib = if ($osDrive) { [math]::Round([double]$osDrive.FreeSpace / 1GB, 1) } else { $null }
    hyperv_installed = $hyperv
    failover_cluster_role_installed = $cluster
    pending_reboot_indicators = $pendingReboot
    hyperv_vm_count = $vmCount
    hyperv_running_vm_count = $activeVMs
    hyperv_checkpoint_count = $checkpointCount
    upgrade_executed = $false
    verdict = 'Inventory only: verify roles, backup/restore, licenses, ISO, drivers and maintenance window before upgrade.'
}
if ($AsJson) {
    $result | ConvertTo-Json -Depth 4
} else {
    foreach ($key in $result.Keys) { Write-Output ("{0}: {1}" -f $key, $result[$key]) }
}
if ($RequireServer -and -not $isServer) { exit 2 }
