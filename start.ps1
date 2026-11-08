# Starts the backend (port 8000) and frontend (port 5173) in their own windows.
$root = $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "First run: creating the Python environment..."
    python -m venv (Join-Path $root "backend\.venv")
    & $python -m pip install --quiet -r (Join-Path $root "backend\requirements.txt")
}
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "First run: installing frontend packages..."
    Push-Location (Join-Path $root "frontend")
    npm install
    Pop-Location
}

Start-Process powershell -WorkingDirectory (Join-Path $root "backend") -ArgumentList "-NoExit", "-Command", "& '$python' -m uvicorn app.main:app --port 8000"
Start-Process powershell -WorkingDirectory (Join-Path $root "frontend") -ArgumentList "-NoExit", "-Command", "npm run dev"

Write-Host "Backend:  http://127.0.0.1:8000/docs"
Write-Host "Frontend: http://localhost:5173"
