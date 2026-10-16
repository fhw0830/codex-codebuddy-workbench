param([switch]$NoBrowser, [switch]$Offline)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = $env:CODEDUO_PYTHON
if (-not $pythonPath) {
    $localPython = Join-Path $appRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) { $pythonPath = $localPython }
}
if (-not $pythonPath) {
    $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Source -notmatch 'WindowsApps') { $pythonPath = $candidate.Source }
}
if (-not $pythonPath) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $resolved = & $launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonPath = [string]($resolved | Select-Object -Last 1) }
    }
}
if (-not $pythonPath -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Install Python 3.12+ or set CODEDUO_PYTHON to its executable.' }
& $pythonPath -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
$serverArgs = @((Join-Path $appRoot 'server.py'))
if (-not $NoBrowser) { $serverArgs += '--open' }
if ($Offline) { $serverArgs += '--offline' }
Write-Output 'CodeDuo - Codex x CodeBuddy. Press Ctrl+C to stop.'
Push-Location -LiteralPath $appRoot
try { & $pythonPath @serverArgs }
finally { Pop-Location }
