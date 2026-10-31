#Requires -Version 5.1
<#
.SYNOPSIS
  Review or explicitly enable selected Windows security audit logging.
.DESCRIPTION
  Default is read-only Status. Enable requires -Apply, administrator rights,
  selected switches and confirmation. Backs up local audit policy and the
  script-block-logging registry value BEFORE any change. No firewall/RDP change.
  PowerShell logs may contain secrets; review collection and retention first.
.EXAMPLE
  .\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Enable -EnableFailedLogonAudit
.EXAMPLE
  .\Set-RedTeamDefenseSecurityLogging.ps1 -Mode Enable -EnableFailedLogonAudit -Apply -Confirm:$false
#>
[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param(
    [ValidateSet('Status','Enable')]
    [string]$Mode = 'Status',
    [switch]$EnableFailedLogonAudit,
    [switch]$EnableScriptBlockLogging,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This tool supports Windows only.' }

# Stable auditing subcategory GUID: Audit_Logon_Logon, independent of OS language.
$logonGuid = '{0cce9215-69ae-11d9-bed3-505054503030}'
$regPath = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging'
$dataDir = Join-Path $env:ProgramData 'RedTeamDefense'
$backupRoot = Join-Path $dataDir 'Backups'

function Test-Admin {
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Get-RegistryState {
    $keyExists = Test-Path -LiteralPath $regPath
    $valueExists = $false
    $oldValue = $null
    if ($keyExists) {
        $property = Get-ItemProperty -LiteralPath $regPath -Name 'EnableScriptBlockLogging' -ErrorAction SilentlyContinue
        if ($null -ne $property -and $null -ne $property.EnableScriptBlockLogging) {
            $valueExists = $true
            $oldValue = [int]$property.EnableScriptBlockLogging
        }
    }
    return [pscustomobject]@{
        KeyExisted = $keyExists
        ValueExisted = $valueExists
        OldValue = $oldValue
    }
}
$registry = Get-RegistryState

if ($Mode -eq 'Status') {
    Write-Output ('Script block logging registry policy: {0}' -f $(if ($registry.ValueExisted) { $registry.OldValue } else { 'not set' }))
    Write-Output ('Audit Logon subcategory (GUID {0}):' -f $logonGuid)
    & auditpol.exe /get "/subcategory:$logonGuid"
    if ($LASTEXITCODE -ne 0) { throw 'Could not read auditpol policy; run elevated if required.' }
    Write-Output 'Status is informational; GPO/MDM may override local settings.'
    return
}
if (-not $EnableFailedLogonAudit -and -not $EnableScriptBlockLogging) {
    throw 'Select -EnableFailedLogonAudit and/or -EnableScriptBlockLogging.'
}
if (-not $Apply) {
    Write-Output ('PLAN only: failed logon auditing={0}, script block logging={1}.' -f $EnableFailedLogonAudit, $EnableScriptBlockLogging)
    Write-Output 'No policy changed. Use -Apply on an authorized Windows Server after review.'
    return
}
if (-not (Test-Admin)) { throw 'Run as administrator on your authorized Windows Server.' }
if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) {
    throw 'Install RedTeamDefense first to provision protected local backup storage.'
}

if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Back up current policy, then enable selected security logging')) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-ffff'
    $backupDir = Join-Path $backupRoot ("SecurityLogging-$stamp")
    New-Item -ItemType Directory -Path $backupDir -ErrorAction Stop | Out-Null
    $registryFile = Join-Path $backupDir 'script-block-policy-before.json'
    $registry | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $registryFile -Encoding UTF8
    $auditFile = Join-Path $backupDir 'audit-policy-before.csv'
    & auditpol.exe /backup "/file:$auditFile" | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $auditFile)) {
        throw 'Audit policy backup failed; no settings were changed.'
    }
    if ($EnableFailedLogonAudit) {
        # Keep current Success setting unchanged. Change Failure only.
        & auditpol.exe /set "/subcategory:$logonGuid" /failure:enable | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed to enable failure-audit policy. See the local backup.' }
    }
    if ($EnableScriptBlockLogging) {
        if (-not (Test-Path -LiteralPath $regPath)) {
            New-Item -Path $regPath -Force -ErrorAction Stop | Out-Null
        }
        New-ItemProperty -LiteralPath $regPath -Name 'EnableScriptBlockLogging' -Value 1 -PropertyType DWord -Force -ErrorAction Stop | Out-Null
    }
    Write-Output ("Selected logging policies requested. Local backup: {0}" -f $backupDir)
    Write-Output 'Check resulting effective policy; domain GPO/MDM may override local changes.'
    Write-Warning 'Script block logs may contain sensitive script content. Secure and retain logs appropriately.'
    Write-Warning 'Manual rollback steps are in docs/REDTEAM_DEFENSE_SERVER_INSTALL.md. Full auditpol restore affects ALL audit policies.'
}
