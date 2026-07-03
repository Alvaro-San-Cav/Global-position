<#
  run.ps1 — convenience launcher for Global Position.

  Usage (always run from the repo root, e.g. C:\Proyectos\FIN\Global-Position):
    .\run.ps1 dev     # backend (uvicorn reload) + frontend (vite) together
    .\run.ps1 build   # build the frontend into frontend/dist
    .\run.ps1 serve   # serve the built app via FastAPI on :8000 (default)
    .\run.ps1 test    # backend pytest + frontend vitest

  The script never changes your shell's current directory: it uses
  Push-Location/Pop-Location internally so you can re-run it back-to-back.
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
        # Backend in a separate window; frontend (vite) in this one.
        Start-Process powershell -ArgumentList @(
            '-NoExit', '-Command',
            "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root\backend'; python -m uvicorn server:app --reload --port 8000"
        )
        Push-Location "$root\frontend"
        try { pnpm dev } finally { Pop-Location }
    }
    'build' {
        Push-Location "$root\frontend"
        try { pnpm build } finally { Pop-Location }
    }
    'serve' {
        # server.py resolves its own paths via __file__, so cwd is irrelevant.
        python "$root\backend\server.py"
    }
    'test' {
        Push-Location "$root\backend"
        try { python -m pytest tests/ -q } finally { Pop-Location }
        Push-Location "$root\frontend"
        try { pnpm test run } finally { Pop-Location }
    }
}
