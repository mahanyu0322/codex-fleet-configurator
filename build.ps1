$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    python (Join-Path $taskRoot 'build.py')
    if ($LASTEXITCODE -ne 0) { throw '程序包构建或验证失败。' }
    Get-ChildItem -LiteralPath (Join-Path $taskRoot 'dist\release') | Select-Object Name, Length
}
finally {
    Pop-Location
}
