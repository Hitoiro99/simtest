param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $SimtestArguments
)
$taskRoot = $PSScriptRoot
$pathForWsl = $taskRoot.Replace('\', '/')
$linuxTaskRootOutput = & wsl -d Ubuntu -- wslpath -u $pathForWsl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$linuxTaskRoot = ($linuxTaskRootOutput -join "`n").Trim()
& wsl -d Ubuntu --cd $linuxTaskRoot -- python3 -m simtest @SimtestArguments
exit $LASTEXITCODE
