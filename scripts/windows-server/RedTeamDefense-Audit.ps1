#Requires -Version 5.1
<#
.SYNOPSIS
  Read-only Windows security readiness audit for authorized local systems.
.DESCRIPTION
  Checks Windows Firewall, Microsoft Defender, RDP/NLA, SMBv1 server configuration,
  PowerShell script block logging policy, selected local TCP listeners, and recent
  failed logon/service-installation events. Saves local HTML, JSON, and CSV reports.
  Does NOT change settings, connect to external hosts, or attempt exploitation.
.EXAMPLE
  .\RedTeamDefense-Audit.ps1 -LookbackHours 24 -FailedLogonThreshold 5
#>
[CmdletBinding()]
param(
    [ValidateRange(1,168)]
    [int]$LookbackHours = 24,

    [ValidateRange(1,10000)]
    [int]$FailedLogonThreshold = 5,

    [string]$OutputDirectory = (Join-Path $env:USERPROFILE 'RedTeamDefense-Reports')
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'This script supports Windows only.'
}

$script:findings = New-Object 'System.Collections.Generic.List[object]'
$startTime = (Get-Date).AddHours(-$LookbackHours)
$eventLimit = 5000

function Add-Finding {
    param(
        [string]$Id,
        [string]$Check,
        [ValidateSet('PASS','WARN','REVIEW','UNKNOWN')][string]$Status,
        [string]$Detail,
        [string]$Recommendation
    )
    $script:findings.Add([pscustomobject]@{
        Id = $Id
        Check = $Check
        Status = $Status
        Detail = $Detail
        Recommendation = $Recommendation
    })
}

function Add-Unknown {
    param([string]$Id, [string]$Check, [System.Management.Automation.ErrorRecord]$Problem)
    Add-Finding -Id $Id -Check $Check -Status 'UNKNOWN' `
        -Detail ("Could not read this setting: " + $Problem.Exception.Message) `
        -Recommendation 'Check OS support, access rights, and required Windows services/modules.'
}

# 1. Effective firewall profiles
try {
    $profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
    if ($profiles.Count -eq 0) {
        Add-Finding 'FW' 'Windows Firewall profiles' 'UNKNOWN' 'No firewall profiles returned.' 'Check the NetSecurity module and local policy.'
    } else {
        $off = @($profiles | Where-Object { $_.Enabled -ne $true } | ForEach-Object { [string]$_.Name })
        $details = ($profiles | ForEach-Object { "{0}={1}" -f $_.Name, $_.Enabled }) -join ', '
        if ($off.Count -gt 0) {
            Add-Finding 'FW' 'Windows Firewall profiles' 'WARN' $details 'Review disabled profiles and enable the appropriate firewall protections under your policy.'
        } else {
            Add-Finding 'FW' 'Windows Firewall profiles' 'PASS' $details 'Keep profiles enabled; verify individual inbound allow rules separately.'
        }
    }
} catch { Add-Unknown 'FW' 'Windows Firewall profiles' $_ }

# 2. Defender: third-party antivirus may legitimately put Defender in passive mode
try {
    $defender = Get-MpComputerStatus -ErrorAction Stop
    if ($null -eq $defender -or $null -eq $defender.RealTimeProtectionEnabled) {
        Add-Finding 'AV' 'Microsoft Defender real-time protection' 'UNKNOWN' 'Defender state was not returned.' 'Verify the installed endpoint protection solution.'
    } elseif ($defender.RealTimeProtectionEnabled -eq $true) {
        Add-Finding 'AV' 'Microsoft Defender real-time protection' 'PASS' 'Real-time protection is enabled.' 'Keep signature/platform updates and tamper protection current.'
    } else {
        Add-Finding 'AV' 'Microsoft Defender real-time protection' 'REVIEW' 'Defender real-time protection is not enabled.' 'Check whether an approved third-party antivirus/EDR is active before changing anything.'
    }
} catch { Add-Unknown 'AV' 'Microsoft Defender real-time protection' $_ }

# 3. RDP and Network Level Authentication
try {
    $rdpKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
    $rdpDisabled = (Get-ItemProperty -LiteralPath $rdpKey -Name 'fDenyTSConnections' -ErrorAction Stop).fDenyTSConnections
    if ([int]$rdpDisabled -eq 1) {
        Add-Finding 'RDP' 'Remote Desktop (RDP)' 'PASS' 'RDP policy disallows inbound remote desktop connections.' 'Enable only when necessary and with a restricted access path.'
    } else {
        Add-Finding 'RDP' 'Remote Desktop (RDP)' 'REVIEW' 'RDP policy allows remote desktop connections (actual service reachability is not verified).' 'Restrict access via network controls, use MFA-capable access gateways, and review authorized users.'
        try {
            $nlaKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp'
            $nla = (Get-ItemProperty -LiteralPath $nlaKey -Name 'UserAuthentication' -ErrorAction Stop).UserAuthentication
            if ([int]$nla -eq 1) {
                Add-Finding 'NLA' 'RDP Network Level Authentication' 'PASS' 'NLA is required.' 'Keep NLA enabled for systems using RDP.'
            } else {
                Add-Finding 'NLA' 'RDP Network Level Authentication' 'WARN' 'NLA is not required.' 'Review RDP policy and require NLA where supported.'
            }
        } catch { Add-Unknown 'NLA' 'RDP Network Level Authentication' $_ }
    }
} catch { Add-Unknown 'RDP' 'Remote Desktop (RDP)' $_ }

# 4. SMBv1 server-side protocol
try {
    $smb = Get-SmbServerConfiguration -ErrorAction Stop
    if ($null -eq $smb -or $null -eq $smb.EnableSMB1Protocol) {
        Add-Finding 'SMB1' 'SMBv1 server protocol' 'UNKNOWN' 'SMBv1 state not available.' 'Review Windows feature and SMB server configuration.'
    } elseif ($smb.EnableSMB1Protocol -eq $true) {
        Add-Finding 'SMB1' 'SMBv1 server protocol' 'WARN' 'The SMBv1 server protocol is enabled.' 'Plan to disable SMBv1 after validating legacy application compatibility.'
    } else {
        Add-Finding 'SMB1' 'SMBv1 server protocol' 'PASS' 'The SMBv1 server protocol is disabled.' 'Also check SMBv1 client components if applicable.'
    }
} catch { Add-Unknown 'SMB1' 'SMBv1 server protocol' $_ }

# 5. Script block logging policy; indicates policy configuration, not proof of ingestion
try {
    $loggingKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging'
    $scriptBlockEnabled = $false
    if (Test-Path -LiteralPath $loggingKey) {
        $loggingValue = Get-ItemProperty -LiteralPath $loggingKey -Name 'EnableScriptBlockLogging' -ErrorAction SilentlyContinue
        if ($null -ne $loggingValue -and [int]$loggingValue.EnableScriptBlockLogging -eq 1) {
            $scriptBlockEnabled = $true
        }
    }
    if ($scriptBlockEnabled) {
        Add-Finding 'PSLOG' 'PowerShell script block logging policy' 'PASS' 'Machine policy explicitly enables script block logging.' 'Ensure event collection, retention, and access controls are configured.'
    } else {
        Add-Finding 'PSLOG' 'PowerShell script block logging policy' 'REVIEW' 'Machine policy does not explicitly enable full script block logging.' 'Consider enabling via a managed policy after privacy, performance, and retention review.'
    }
} catch { Add-Unknown 'PSLOG' 'PowerShell script block logging policy' $_ }

# 6. Local TCP listeners: these are NOT proof of public/internet exposure
try {
    $watchPorts = @(22,445,3389,5985,5986)
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $watchPorts -contains [int]$_.LocalPort })
    if ($listeners.Count -eq 0) {
        Add-Finding 'PORTS' 'Selected local TCP listeners' 'PASS' 'No listeners found on ports 22, 445, 3389, 5985, 5986.' 'Review other services and firewall rules according to your environment.'
    } else {
        foreach ($port in $watchPorts) {
            $matches = @($listeners | Where-Object { [int]$_.LocalPort -eq $port })
            if ($matches.Count -eq 0) { continue }
            $addresses = @($matches | Select-Object -ExpandProperty LocalAddress -Unique)
            $addressText = ($addresses -join ', ')
            $wide = @($addresses | Where-Object { $_ -eq '0.0.0.0' -or $_ -eq '::' }).Count -gt 0
            $boundType = if ($wide) { 'includes wildcard interface bind' } else { 'specific interface bind' }
            Add-Finding ("PORT-{0}" -f $port) ("TCP listener {0}" -f $port) 'REVIEW' `
                ("Local addresses: {0}; {1}. This does not confirm external access." -f $addressText, $boundType) `
                'Verify the service is required and check firewall, VLAN, VPN, and gateway access controls.'
        }
    }
} catch { Add-Unknown 'PORTS' 'Selected local TCP listeners' $_ }

# 7. Failed logons, Security event 4625
try {
    $failedLogons = @(Get-WinEvent -FilterHashtable @{
        LogName = 'Security'; Id = 4625; StartTime = $startTime
    } -MaxEvents $eventLimit -ErrorAction Stop)

    $ipAddresses = @(
        foreach ($entry in $failedLogons) {
            try {
                [xml]$entryXml = $entry.ToXml()
                $ipNode = $entryXml.SelectSingleNode("//*[local-name()='Data' and @Name='IpAddress']")
                if ($null -ne $ipNode) {
                    $ip = [string]$ipNode.InnerText
                    if (-not [string]::IsNullOrWhiteSpace($ip) -and $ip -ne '-') { $ip }
                }
            } catch { }
        }
    )
    $ipGroups = @($ipAddresses | Group-Object | Sort-Object Count -Descending | Select-Object -First 5)
    $topSources = ($ipGroups | ForEach-Object { "{0}: {1}" -f $_.Name, $_.Count }) -join '; '
    if ([string]::IsNullOrWhiteSpace($topSources)) { $topSources = 'no source IP recorded' }
    $capNote = if ($failedLogons.Count -ge $eventLimit) { ' Event collection reached the 5000-record limit; counts may be partial.' } else { '' }
    $message = "Failed logons in last $LookbackHours hours: $($failedLogons.Count). Top source IPs: $topSources.$capNote"
    $status = if ($failedLogons.Count -ge $FailedLogonThreshold) { 'WARN' } else { 'REVIEW' }
    Add-Finding 'AUTH' 'Failed logons (Security 4625)' $status $message `
        'Review source hosts and account lockout policies; failures alone do not prove an attack.'
} catch {
    if ($_.FullyQualifiedErrorId -like '*NoMatchingEventsFound*') {
        Add-Finding 'AUTH' 'Failed logons (Security 4625)' 'REVIEW' `
            "No 4625 events found in the last $LookbackHours hours (audit coverage is not verified)." `
            'Verify failed-logon audit policy and Security log retention.'
    } else {
        Add-Unknown 'AUTH' 'Failed logons (Security 4625)' $_
    }
}

# 8. New service installations, System event 7045: review only; many are legitimate
try {
    $serviceEvents = @(Get-WinEvent -FilterHashtable @{
        LogName = 'System'; Id = 7045; StartTime = $startTime
    } -MaxEvents 500 -ErrorAction Stop)
    $names = @($serviceEvents | Select-Object -First 8 | ForEach-Object {
        if ($_.Properties.Count -gt 0) { [string]$_.Properties[0].Value }
    })
    $sample = if ($names.Count -gt 0) { $names -join ', ' } else { 'not available' }
    Add-Finding 'SVC' 'Newly installed services (System 7045)' 'REVIEW' `
        "Service installation events in last $LookbackHours hours: $($serviceEvents.Count). Recent names: $sample." `
        'Compare against approved software installs and change records; these events are not automatically malicious.'
} catch {
    if ($_.FullyQualifiedErrorId -like '*NoMatchingEventsFound*') {
        Add-Finding 'SVC' 'Newly installed services (System 7045)' 'REVIEW' `
            "No service installation events found in the last $LookbackHours hours." `
            'Event absence is not proof that all persistence techniques were prevented.'
    } else {
        Add-Unknown 'SVC' 'Newly installed services (System 7045)' $_
    }
}

# Write reports only under the caller-selected local directory
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$prefix = Join-Path $OutputDirectory ("RedTeamDefense-{0}" -f $stamp)
$allFindings = @($script:findings.ToArray())
$counts = [ordered]@{}
foreach ($state in @('PASS','WARN','REVIEW','UNKNOWN')) {
    $counts[$state] = @($allFindings | Where-Object { $_.Status -eq $state }).Count
}
$report = [ordered]@{
    Tool = 'RedTeamDefense-Audit'
    Version = '1.0.0'
    Hostname = $env:COMPUTERNAME
    GeneratedAtLocal = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    LookbackHours = $LookbackHours
    FailedLogonThreshold = $FailedLogonThreshold
    Summary = $counts
    Notes = @(
        'Read-only local audit; no vulnerability exploit or external network scan performed.',
        'A listening port does not establish internet exposure.',
        'UNKNOWN and REVIEW findings require manual verification; WARN is not proof of compromise.',
        'Report may contain local IP addresses and service names; store securely.'
    )
    Findings = $allFindings
}
$jsonFile = "$prefix.json"
$csvFile = "$prefix.csv"
$htmlFile = "$prefix.html"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonFile -Encoding UTF8
$allFindings | Export-Csv -LiteralPath $csvFile -NoTypeInformation -Encoding UTF8

function Escape-Html([string]$Value) {
    return [System.Net.WebUtility]::HtmlEncode($Value)
}
$rows = ($allFindings | ForEach-Object {
    $status = Escape-Html ([string]$_.Status)
    $check = Escape-Html ([string]$_.Check)
    $detail = Escape-Html ([string]$_.Detail)
    $advice = Escape-Html ([string]$_.Recommendation)
    "<tr><td><strong>$status</strong></td><td>$check</td><td>$detail</td><td>$advice</td></tr>"
}) -join "`r`n"
$titleHost = Escape-Html $env:COMPUTERNAME
$generated = Escape-Html $report.GeneratedAtLocal
$html = @"
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedTeamDefense Audit</title>
<style>
body{font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;margin:32px auto;max-width:1180px;padding:0 18px;color:#172034;background:#f8fafc}
h1{margin-bottom:4px}p{line-height:1.6} .meta{color:#4b5563}
.summary{padding:18px 22px;background:white;border:1px solid #d7dee8;border-radius:10px;margin:22px 0}
table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #d7dee8;padding:12px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e8eef6}
.note{font-size:14px;color:#4b5563;margin-top:24px}
</style>
</head>
<body>
<h1>RedTeamDefense | Windows Security Audit</h1>
<p class="meta">Host: $titleHost | Generated: $generated | Lookback: $LookbackHours hours</p>
<div class="summary"><strong>Summary</strong><p>PASS: $($counts['PASS']) &nbsp; WARN: $($counts['WARN']) &nbsp; REVIEW: $($counts['REVIEW']) &nbsp; UNKNOWN: $($counts['UNKNOWN'])</p></div>
<table><thead><tr><th>Status</th><th>Check</th><th>Observation</th><th>Recommendation</th></tr></thead><tbody>
$rows
</tbody></table>
<p class="note">Read-only check. An open local port does not establish internet access. WARN does not prove a breach. Event logs can be incomplete. Handle this local report as sensitive information.</p>
</body></html>
"@
$html | Set-Content -LiteralPath $htmlFile -Encoding UTF8

Write-Host "`nRedTeamDefense Audit finished (read-only)." -ForegroundColor Cyan
Write-Host ("PASS={0} WARN={1} REVIEW={2} UNKNOWN={3}" -f $counts['PASS'], $counts['WARN'], $counts['REVIEW'], $counts['UNKNOWN'])
Write-Host "HTML: $htmlFile"
Write-Host "JSON: $jsonFile"
Write-Host "CSV : $csvFile"
$allFindings | Format-Table Status, Check, Detail -Wrap -AutoSize