$env:LAYADESK_MODE = 'laya'
$env:LAYADESK_DB = "$PSScriptRoot\layadesk-cuda.db"
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\scripts\check_cuda.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
