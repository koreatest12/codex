#Requires -Version 5.1
<#
.SYNOPSIS
Manages the Linux WAS inside a separately installed Ubuntu VM via verified SSH.
.DESCRIPTION
A pinned allowlist of remote actions, SSH public key verification and user-provided
identity file prevent exposing Docker's TCP socket or uploading credentials.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('Clone', 'InstallDocker', 'InitLocal', 'Doctor', 'Deploy', 'Start', 'Stop', 'Restart', 'Status', 'Health', 'Backup', 'Upgrade', 'Tunnel')]
    [string]$Action,
    [Parameter(Mandatory)][string]$LinuxHost,
    [Parameter(Mandatory)][string]$LinuxUser,
    [Parameter(Mandatory)][string]$IdentityFile,
    [ValidateRange(1024,65535)][int]$LocalPort = 8080
)

$ErrorActionPreference = 'Stop'
if ($LinuxHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$' -or $LinuxHost.Contains('..')) {
    throw 'Invalid LinuxHost. Use the numeric IPv4 address or trusted DNS name of the Ubuntu VM.'
}
if ($LinuxUser -notmatch '^[a-z_][a-z0-9_-]{0,31}$') {
    throw 'Invalid LinuxUser. Supply the non-root Ubuntu login account.'
}
$key = Get-Item -LiteralPath $IdentityFile -ErrorAction Stop
if ($key.PSIsContainer) { throw 'IdentityFile must be an existing SSH private-key file.' }
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    throw 'OpenSSH Client (ssh.exe) is required on Windows Server.'
}
$destination = "$LinuxUser@$LinuxHost"
$argsList = @('-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15', '-i', $key.FullName)
if ($Action -eq 'Tunnel') {
    Write-Output "Establishing localhost-only port forwarding on 127.0.0.1:$LocalPort. Ctrl+C to stop."
    Write-Output "Open http://localhost:$LocalPort in a browser on THIS Windows host."
    & ssh.exe @argsList -N -T -L "127.0.0.1:$($LocalPort):127.0.0.1:8080" $destination
    exit $LASTEXITCODE
}
# All commands below are literal, not built from shell fragments supplied by users.
$commands = @{
    Clone = 'test ! -e "$HOME/codex" && git clone https://github.com/koreatest12/codex.git "$HOME/codex"'
    InstallDocker = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py install-docker'
    InitLocal = 'cd "$HOME/codex" && python3 scripts/was-manager.py init --rp-id localhost --origin http://localhost:8080'
    Doctor = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py doctor'
    Deploy = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py deploy'
    Start = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py start'
    Stop = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py stop'
    Restart = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py restart'
    Status = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py status'
    Health = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py health'
    Backup = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py backup'
    Upgrade = 'cd "$HOME/codex" && sudo python3 scripts/was-manager.py upgrade'
}
Write-Output "SSH action: $Action on $LinuxHost (no automatic firewall or external port changes)"
# Allocate tty so sudo can request consent/password on the guest as configured.
& ssh.exe @argsList -tt $destination $commands[$Action]
exit $LASTEXITCODE
