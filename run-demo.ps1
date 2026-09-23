$env:LAYADESK_MODE = 'demo'
$env:LAYADESK_DB = "$PSScriptRoot\layadesk-demo.db"
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
