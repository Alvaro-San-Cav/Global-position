<#
  launch-app.ps1 - arranca Global Position y lo abre en Chrome como app.

  - Si /api/health no responde en 127.0.0.1:8000, levanta el servidor en
    segundo plano (ventana oculta) con el python del venv si existe
    (<repo>\..\.venv o <repo>\.venv; si no, 'python' del PATH).
  - Guarda el PID en processing\server.pid y la salida en processing\server.log
    (stdout) y processing\server.err.log (stderr).
  - Si el puerto 8000 esta ocupado por algo que NO responde a /api/health,
    avisa y no abre la app.
  - Espera a /api/health y abre Chrome en modo --app.

  Uso:
    .\launch-app.ps1          # arrancar (si hace falta) y abrir
    .\launch-app.ps1 -Stop    # parar el servidor lanzado por este script (por PID)

  Pensado para el acceso directo del escritorio (create-desktop-shortcut.ps1).
#>
param(
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root     = $PSScriptRoot
$hostAddr = '127.0.0.1'
$port     = 8000
$url      = "http://${hostAddr}:$port"
$procDir  = Join-Path $root 'processing'
$pidFile  = Join-Path $procDir 'server.pid'
$logOut   = Join-Path $procDir 'server.log'
$logErr   = Join-Path $procDir 'server.err.log'

function Show-Error([string]$msg) {
    Write-Warning $msg
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($msg, 'Global Position', 'OK', 'Error') | Out-Null
    } catch {}
}

# Estado del servidor: 'ok' (health 200), 'other' (puerto ocupado por otra cosa), 'down'
function Get-ServerState {
    $listening = $false
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect($hostAddr, $port)
        $c.Close()
        $listening = $true
    } catch {}
    if (-not $listening) { return 'down' }
    try {
        $r = Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { return 'ok' }
    } catch {}
    return 'other'
}

# -- Modo -Stop ------------------------------------------------------------
if ($Stop) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        Write-Host "No hay ${pidFile}: nada que parar (el servidor no fue lanzado por este script)."
        exit 0
    }
    $savedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($savedPid -match '^\d+$' -and (Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue)) {
        # /T mata tambien el proceso hijo (el launcher del venv lanza python real)
        & taskkill.exe /PID $savedPid /T /F | Out-Null
        Write-Host "Servidor parado (PID $savedPid)."
    } else {
        Write-Host "El proceso $savedPid ya no existe."
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

# -- 0. Reconstruir el frontend si el codigo es mas nuevo que el build -----
function Update-FrontendBuild {
    $feDir = Join-Path $root 'frontend'
    $src   = Join-Path $feDir 'src'
    $dist  = Join-Path $feDir 'dist\index.html'
    if (-not (Test-Path -LiteralPath $src)) { return }

    $needsBuild = $true
    if (Test-Path -LiteralPath $dist) {
        $distTime = (Get-Item -LiteralPath $dist).LastWriteTimeUtc
        $newest = Get-ChildItem -LiteralPath $src -Recurse -File -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        $needsBuild = $newest -and ($newest.LastWriteTimeUtc -gt $distTime)
    }
    if (-not $needsBuild) { return }

    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        Write-Warning 'pnpm no esta instalado: se abre el build existente (puede estar desactualizado).'
        return
    }
    if (-not (Test-Path -LiteralPath (Join-Path $feDir 'node_modules'))) {
        Write-Warning 'Falta frontend\node_modules (ejecuta "pnpm install" en frontend). Se abre el build existente.'
        return
    }

    Push-Location -LiteralPath $feDir
    try {
        Write-Host 'Reconstruyendo frontend (cambios detectados)...'
        & pnpm build | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "pnpm build fallo (codigo $LASTEXITCODE): se abre el build anterior. Ejecuta 'pnpm build' en frontend para ver el error."
        }
    } catch {
        Write-Warning "Fallo al reconstruir el frontend: $_"
    } finally {
        Pop-Location
    }
}

Update-FrontendBuild

# -- 1. Levantar el servidor si hace falta ---------------------------------
$state = Get-ServerState
if ($state -eq 'other') {
    Show-Error "El puerto $port esta ocupado por otro proceso que no responde a $url/api/health. Cierralo (o usa '.\launch-app.ps1 -Stop' si lo lanzo este script) y reintenta."
    exit 1
}

if ($state -eq 'down') {
    $py = 'python'
    foreach ($cand in @((Join-Path $root '..\.venv\Scripts\python.exe'),
                        (Join-Path $root '.venv\Scripts\python.exe'))) {
        if (Test-Path -LiteralPath $cand) { $py = (Resolve-Path -LiteralPath $cand).Path; break }
    }

    if (-not (Test-Path -LiteralPath $procDir)) {
        New-Item -ItemType Directory -Path $procDir -Force | Out-Null
    }

    # PYTHONIOENCODING solo para el hijo: se restaura el valor del padre al terminar.
    $prevEnc = $env:PYTHONIOENCODING
    $env:PYTHONIOENCODING = 'utf-8'
    try {
        $proc = Start-Process -FilePath $py `
            -ArgumentList "`"$root\backend\server.py`"" `
            -WorkingDirectory (Join-Path $root 'backend') `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $logOut -RedirectStandardError $logErr
    } finally {
        if ($null -eq $prevEnc) { Remove-Item Env:\PYTHONIOENCODING -ErrorAction SilentlyContinue }
        else { $env:PYTHONIOENCODING = $prevEnc }
    }
    Set-Content -LiteralPath $pidFile -Value $proc.Id -Encoding ascii

    # Esperar hasta 30 s a que la API responda
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        if ($proc.HasExited) { break }
        if ((Get-ServerState) -eq 'ok') { $ok = $true; break }
    }
    if (-not $ok) {
        Show-Error "El servidor de Global Position no arranco.`nRevisa el log:`n$logErr`n$logOut"
        exit 1
    }
}

# -- 2. Abrir Chrome en modo app -------------------------------------------
$chrome = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'(default)'
if (-not $chrome -or -not (Test-Path -LiteralPath $chrome)) {
    $chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path -LiteralPath $chrome)) {
    Start-Process $url   # sin Chrome: navegador por defecto
    exit 0
}

Start-Process -FilePath $chrome -ArgumentList "--app=$url", '--window-size=1440,900'
