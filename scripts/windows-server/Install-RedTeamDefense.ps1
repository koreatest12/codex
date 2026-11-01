#Requires -Version 5.1
<#
.SYNOPSIS
  Installs a local scheduled, read-only RedTeamDefense audit on Windows Server.
.DESCRIPTION
  Status is read-only. Install/Uninstall require both -Apply and elevation.
  Installs NO web server, VM, network listener, firewall rule, or remote connection.
  Reports and backups remain on the local host; uninstall preserves data.
.EXAMPLE
  .\Install-RedTeamDefense.ps1 -Mode Install
.EXAMPLE
  .\Install-RedTeamDefense.ps1 -Mode Install -Apply -Confirm:$false
#>
[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param(
    [ValidateSet('Status','Install','Uninstall')]
    [string]$Mode = 'Status',
    [switch]$Apply,
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$DailyAt = '03:00',
    [ValidateRange(1,168)]
    [int]$LookbackHours = 24,
    [ValidateRange(1,10000)]
    [int]$FailedLogonThreshold = 5
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'RedTeamDefense-Storage.ps1')
if ($env:OS -ne 'Windows_NT') { throw 'This tool supports Windows only.' }
$installDir = Join-Path $env:ProgramFiles 'RedTeamDefense'
$dataDir = Join-Path $env:ProgramData 'RedTeamDefense'
$reportsDir = Join-Path $dataDir 'Reports'
$backupsDir = Join-Path $dataDir 'Backups'
$installedScript = Join-Path $installDir 'RedTeamDefense-Audit.ps1'
$sourceScript = Join-Path $PSScriptRoot 'RedTeamDefense-Audit.ps1'
$taskPath = '\RedTeamDefense\'
$taskName = 'DailyAudit'

function Test-Elevated {
    $who = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($who)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Get-AuditTask {
    return Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
}

$existingTask = Get-AuditTask
if ($Mode -eq 'Status') {
    [pscustomobject]@{
        InstalledFile = Test-Path -LiteralPath $installedScript -PathType Leaf
        ScheduledTask = ($null -ne $existingTask)
        TaskState = if ($null -ne $existingTask) { [string]$existingTask.State } else { 'NotInstalled' }
        ReportsDirectory = $reportsDir
        ReportsDirectoryExists = Test-Path -LiteralPath $reportsDir -PathType Container
        SecurityPolicyChanged = $false
    } | Format-List
    return
}
if (-not $Apply) {
    Write-Output ("PLAN only: Mode={0}; schedule={1}; installed script={2}" -f $Mode, $DailyAt, $installedScript)
    Write-Output 'Nothing changed. Specify -Apply on the local server to proceed.'
    return
}
if (-not (Test-Elevated)) { throw 'Run Windows PowerShell as administrator.' }

if ($Mode -eq 'Install') {
    if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) {
        throw 'Source script is missing. Run this installer from scripts/windows-server in the checked-out repository.'
    }
    if ($null -ne $existingTask -or (Test-Path -LiteralPath $installDir)) {
        throw 'Existing install/task detected. Refusing to overwrite; investigate or uninstall first.'
    }
    if (Test-Path -LiteralPath $dataDir) {
        # Preserve existing data only after checking all descendants, owners and ACLs.
        Test-RedTeamProtectedDirectory $dataDir -Recursive
        if (Test-Path -LiteralPath $reportsDir) { Test-RedTeamProtectedDirectory $reportsDir }
        if (Test-Path -LiteralPath $backupsDir) { Test-RedTeamProtectedDirectory $backupsDir }
    }
    if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Install protected RedTeamDefense files and daily scheduled audit')) {
        $createdInstallDir = $false
        try {
        # Create each directory with its protected ACL in the same operation.
        New-RedTeamProtectedDirectory $installDir
        $createdInstallDir = $true
        if (-not (Test-Path -LiteralPath $dataDir)) {
            New-RedTeamProtectedDirectory $dataDir
        }
        if (-not (Test-Path -LiteralPath $reportsDir)) { New-RedTeamProtectedDirectory $reportsDir }
        if (-not (Test-Path -LiteralPath $backupsDir)) { New-RedTeamProtectedDirectory $backupsDir }
        Test-RedTeamProtectedDirectory $dataDir -Recursive
        Copy-Item -LiteralPath $sourceScript -Destination $installedScript -ErrorAction Stop
        $exe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arguments = '-NoProfile -NonInteractive -File "{0}" -OutputDirectory "{1}" -LookbackHours {2} -FailedLogonThreshold {3}' -f $installedScript, $reportsDir, $LookbackHours, $FailedLogonThreshold
        $action = New-ScheduledTaskAction -Execute $exe -Argument $arguments
        $time = [datetime]::ParseExact($DailyAt, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
        $trigger = New-ScheduledTaskTrigger -Daily -At $time
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -StartWhenAvailable -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Read-only local Windows security audit. Results remain on the server.' -ErrorAction Stop | Out-Null
        } catch {
            # Remove only the file/directory this attempt created; preserve all data.
            if ($createdInstallDir -and (Test-Path -LiteralPath $installedScript -PathType Leaf)) { Remove-Item -LiteralPath $installedScript -Force -ErrorAction Continue }
            if ($createdInstallDir -and (Test-Path -LiteralPath $installDir -PathType Container)) {
                if (@(Get-ChildItem -LiteralPath $installDir -Force).Count -eq 0) { Remove-Item -LiteralPath $installDir -ErrorAction Continue }
            }
            Write-Warning 'Install did not complete. Preserved data directories. Inspect task, ACLs and folders before retrying.'
            throw
        }
        Write-Output ("Installed scheduled audit at {0} (local time). Reports: {1}" -f $DailyAt, $reportsDir)
        Write-Output 'Security baselines, firewall rules, Defender, RDP, and network settings were NOT changed.'
    }
} elseif ($Mode -eq 'Uninstall') {
    if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Remove RedTeamDefense scheduled task and installed script; preserve reports/backups')) {
        if ($null -ne $existingTask) {
            if (@($existingTask.Actions).Count -ne 1 -or $existingTask.Actions[0].Arguments -notlike ('*' + $installedScript + '*')) { throw 'Existing task does not match this installation; refusing to remove it.' }
            Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction Stop
        }
        if (Test-Path -LiteralPath $installedScript -PathType Leaf) {
            Remove-Item -LiteralPath $installedScript -Force -ErrorAction Stop
        }
        if (Test-Path -LiteralPath $installDir -PathType Container) {
            # Do not recursively delete a directory that may contain other files.
            $remaining = @(Get-ChildItem -LiteralPath $installDir -Force)
            if ($remaining.Count -eq 0) { Remove-Item -LiteralPath $installDir -ErrorAction Stop }
        }
        Write-Output ("Uninstalled task/script. Preserved reports and backups under {0}" -f $dataDir)
    }
}
