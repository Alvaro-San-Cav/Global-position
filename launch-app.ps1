<#
  launch-app.ps1 — arranca Global Position y lo abre en Chrome como app.

  - Si el servidor no está escuchando en :8000, lo levanta en segundo plano
    (ventana oculta) usando el python del venv si existe.
  - Espera a que /api/health responda y abre Chrome en modo --app
    (ventana sin pestañas ni barra de direcciones, como una app de escritorio).

  Pensado para ser invocado desde el acceso directo del escritorio
  (ver create-desktop-shortcut.ps1). También funciona ejecutándolo a mano.
#>

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$url  = 'http://localhost:8000'

# ── 0. Reconstruir el frontend si el código es más nuevo que el build ─────
# Evita abrir una versión vieja tras editar el frontend sin recordar 'build'.
function Update-FrontendBuild {
    $src  = Join-Path $root 'frontend\src'
    $dist = Join-Path $root 'frontend\dist\index.html'
    if (-not (Test-Path $src)) { return }

    $needsBuild = $true
    if (Test-Path $dist) {
        $distTime = (Get-Item $dist).LastWriteTimeUtc
        $newest = Get-ChildItem $src -Recurse -File -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        # Sólo reconstruir si hay fuente más nueva que el build actual.
        $needsBuild = $newest -and ($newest.LastWriteTimeUtc -gt $distTime)
    }
    if (-not $needsBuild) { return }

    $pnpm = (Get-Command pnpm -ErrorAction SilentlyContinue)
    if (-not $pnpm) { return }   # sin pnpm: abrir lo que haya

    Push-Location (Join-Path $root 'frontend')
    try {
        Write-Host 'Reconstruyendo frontend (cambios detectados)...'
        & pnpm build | Out-Null
    } catch {
        Write-Warning "Fallo al reconstruir el frontend: $_"
    } finally {
        Pop-Location
    }
}

Update-FrontendBuild

function Test-Port8000 {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', 8000)
        $c.Close()
        return $true
    } catch { return $false }
}

# ── 1. Levantar el servidor si hace falta ────────────────────────────────
if (-not (Test-Port8000)) {
    $venvPy = 'C:\Proyectos\FIN\.venv\Scripts\python.exe'
    $py = if (Test-Path $venvPy) { $venvPy } else { 'python' }

    # El hijo hereda el entorno del padre (compatible con PowerShell 5.1).
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process -FilePath $py `
        -ArgumentList "`"$root\backend\server.py`"" `
        -WorkingDirectory "$root\backend" `
        -WindowStyle Hidden

    # Esperar hasta 30 s a que la API responda
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $r = Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch {}
    }
    if (-not $ok) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show(
            "El servidor de Global Position no arrancó en 30 s.`nRevisa: python $root\backend\server.py",
            'Global Position', 'OK', 'Error') | Out-Null
        exit 1
    }
}

# ── 2. Abrir Chrome en modo app ──────────────────────────────────────────
$chrome = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'(default)'
if (-not $chrome -or -not (Test-Path $chrome)) {
    $chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $chrome)) {
    # Sin Chrome: abrir en el navegador por defecto
    Start-Process $url
    exit 0
}

Start-Process -FilePath $chrome -ArgumentList "--app=$url", '--window-size=1440,900'
