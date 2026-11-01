# Runs only on a disposable Windows runner. Does not modify audit policies.
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP ('rtd-' + [guid]::NewGuid().ToString('N'))
$oldProgramFiles = $env:ProgramFiles
$oldProgramData = $env:ProgramData
$installer = Join-Path $PWD 'scripts/windows-server/Install-RedTeamDefense.ps1'
$cleanup = Join-Path $PWD 'scripts/windows-server/Remove-RedTeamDefenseExpiredReports.ps1'
$taskPath = '\RedTeamDefense\'
try {
    if (Get-ScheduledTask -TaskPath $taskPath -TaskName DailyAudit -ErrorAction SilentlyContinue) { throw 'Test task already exists.' }
    New-Item -ItemType Directory -Path "$root\pf", "$root\pd" -Force | Out-Null
    $env:ProgramFiles = "$root\pf"
    $env:ProgramData = "$root\pd"
    & $installer -Mode Install -Apply -Confirm:$false
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName DailyAudit
    if ($task.Principal.UserId -notmatch 'SYSTEM|S-1-5-18') { throw 'Unexpected task principal.' }
    $reports = Join-Path $env:ProgramData 'RedTeamDefense\Reports'
    $old = Join-Path $reports 'RedTeamDefense-20000101-000000.json'
    Set-Content -LiteralPath $old -Value '{}' -Encoding UTF8
    (Get-Item -LiteralPath $old).LastWriteTime = (Get-Date).AddDays(-100)
    & $cleanup -RetentionDays 90 | Out-Null
    if (-not (Test-Path $old)) { throw 'Preview removed a report.' }
    & $installer -Mode Uninstall -Apply -Confirm:$false
    if (-not (Test-Path $old)) { throw 'Uninstall removed a report.' }
    & $installer -Mode Install -Apply -Confirm:$false
    if (-not (Test-Path $old)) { throw 'Reinstall removed a report.' }
    & $cleanup -RetentionDays 90 -Apply -Confirm:$false | Out-Null
    if (Test-Path $old) { throw 'Expired report was not removed.' }
    & $installer -Mode Uninstall -Apply -Confirm:$false
    Write-Output 'PASS: install, protected storage, preservation, reinstall and opt-in retention.'
} finally {
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName DailyAudit -ErrorAction SilentlyContinue
    if ($task -and $task.Actions[0].Arguments -like "*$root*") { Unregister-ScheduledTask -TaskPath $taskPath -TaskName DailyAudit -Confirm:$false }
    $env:ProgramFiles = $oldProgramFiles
    $env:ProgramData = $oldProgramData
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
