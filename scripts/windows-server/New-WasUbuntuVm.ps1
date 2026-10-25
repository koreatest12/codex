#Requires -Version 5.1
<#
.SYNOPSIS
Creates a new, unconfigured Ubuntu ISO Hyper-V VM for the existing Linux WAS.
.NOTES
Requires a manually downloaded and checksum-verified Ubuntu Server ISO and an
existing administrator-selected virtual switch. Does not install Ubuntu, Docker,
GitHub code or expose ports. Never overwrites an existing VM or VHD.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$')][string]$VMName,
    [Parameter(Mandatory)][string]$IsoPath,
    [Parameter(Mandatory)][string]$SwitchName,
    [Parameter(Mandatory)][string]$VmRoot,
    [ValidateRange(2,128)][int]$MemoryGB = 4,
    [ValidateRange(30,2048)][int]$DiskGB = 60,
    [ValidateRange(1,64)][int]$CpuCount = 2,
    [switch]$StartVM
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command Get-VM -ErrorAction SilentlyContinue)) {
    throw 'Hyper-V PowerShell management tools are not installed.'
}
if (Get-VM -Name $VMName -ErrorAction SilentlyContinue) {
    throw "A VM already exists with this name. Refusing to modify: $VMName"
}
$iso = Get-Item -LiteralPath $IsoPath -ErrorAction Stop
if ($iso.PSIsContainer -or $iso.Extension -ine '.iso') {
    throw 'Specify an existing Ubuntu Server .iso file.'
}
$vmSwitch = Get-VMSwitch -Name $SwitchName -ErrorAction Stop
if ($null -eq $vmSwitch) { throw 'Selected Hyper-V virtual switch was not found.' }
$root = [System.IO.Path]::GetFullPath($VmRoot)
if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw 'VmRoot must already be an existing directory. Refusing to create unknown host paths.'
}
$vmFolder = Join-Path $root $VMName
$vhd = Join-Path $vmFolder "$VMName.vhdx"
if ((Test-Path -LiteralPath $vmFolder) -or (Test-Path -LiteralPath $vhd)) {
    throw 'The target VM folder/disk exists. Refusing to overwrite.'
}
if ($PSCmdlet.ShouldProcess($VMName, 'Create new Generation 2 Ubuntu VM, virtual disk and ISO attachment')) {
    $newArgs = @{
        Name = $VMName
        Generation = 2
        MemoryStartupBytes = ([UInt64]$MemoryGB * 1GB)
        NewVHDPath = $vhd
        NewVHDSizeBytes = ([UInt64]$DiskGB * 1GB)
        Path = $root
        SwitchName = $SwitchName
    }
    New-VM @newArgs | Out-Null
    Set-VMProcessor -VMName $VMName -Count $CpuCount
    Add-VMDvdDrive -VMName $VMName -Path $iso.FullName
    $dvd = Get-VMDvdDrive -VMName $VMName | Where-Object { $_.Path -eq $iso.FullName } | Select-Object -First 1
    if (-not $dvd) { throw 'Ubuntu installer DVD was not attached; inspect the VM manually.' }
    Set-VMFirmware -VMName $VMName -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority -FirstBootDevice $dvd
    Write-Output "VM provisioned: $VMName. Ubuntu OS installation and SSH configuration are still manual."
    if ($StartVM) {
        Start-VM -Name $VMName | Out-Null
        Write-Output 'VM started. Complete Ubuntu installation through the Hyper-V console.'
    }
}
