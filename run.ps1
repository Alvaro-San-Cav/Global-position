<#
  run.ps1 — convenience launcher for Global Position.

  Usage:
    .\run.ps1 dev     # backend (uvicorn reload) + frontend (vite) together
    .\run.ps1 build   # build the frontend into frontend/dist
    .\run.ps1 serve   # serve the built app via FastAPI on :8000 (default)
    .\run.ps1 test    # backend pytest + frontend vitest
#>
param(
    [ValidateSet('dev', 'build', 'serve', 'test')]
    [string]$cmd = 'serve'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'

switch ($cmd) {
    'dev' {
        Start-Process powershell -ArgumentList @(
            '-NoExit', '-Command',
            "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root\backend'; python -m uvicorn server:app --reload --port 8000"
        )
        Set-Location "$root\frontend"
        pnpm dev
    }
    'build' {
        Set-Location "$root\frontend"
        pnpm build
    }
    'serve' {
        Set-Location "$root\backend"
        python server.py
    }
    'test' {
        Set-Location "$root\backend"
        python -m pytest tests/ -q
        Set-Location "$root\frontend"
        pnpm test run
    }
}
