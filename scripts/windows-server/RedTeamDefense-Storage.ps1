# Shared storage checks. Dot-source only; no operations run on import.
function Test-RedTeamProtectedDirectory([string]$Path, [switch]$Recursive) {
    $allowed = @('S-1-5-18', 'S-1-5-32-544')
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "Missing protected directory: $Path" }
    $items = @((Get-Item -LiteralPath $Path -Force))
    if ($Recursive) { $items += @(Get-ChildItem -LiteralPath $Path -Force -Recurse) }
    foreach ($item in $items) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point is not permitted: $($item.FullName)" }
        $acl = Get-Acl -LiteralPath $item.FullName -ErrorAction Stop
        if (-not $acl.AreAccessRulesProtected -and $item.FullName -eq $Path) { throw "Directory inherits permissions: $Path" }
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        foreach ($rule in $rules) {
            if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Deny -or $rule.IdentityReference.Value -notin $allowed) {
                throw "Unexpected rule in ACL: $($item.FullName) ($($rule.IdentityReference.Value))"
            }
        }
        foreach ($sidText in $allowed) {
            $full = @($rules | Where-Object { $_.IdentityReference.Value -eq $sidText -and ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq [Security.AccessControl.FileSystemRights]::FullControl })
            if ($full.Count -eq 0) { throw "Required full control missing: $($item.FullName) ($sidText)" }
        }
        $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($owner -notin $allowed) { throw "Unexpected owner: $($item.FullName) ($owner)" }
    }
}
function New-RedTeamProtectedDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) { throw "Refusing to overwrite: $Path" }
    $security = New-Object System.Security.AccessControl.DirectorySecurity
    $security.SetAccessRuleProtection($true, $false)
    $admin = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $security.SetOwner($admin)
    foreach ($sidText in @('S-1-5-18', 'S-1-5-32-544')) {
        $sid = New-Object System.Security.Principal.SecurityIdentifier($sidText)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $security.AddAccessRule($rule)
    }
    [IO.Directory]::CreateDirectory($Path, $security) | Out-Null
    Test-RedTeamProtectedDirectory $Path
}
