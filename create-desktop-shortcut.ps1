<#
  create-desktop-shortcut.ps1 — crea "Global Position.lnk" en el escritorio.

  El acceso directo ejecuta launch-app.ps1 (oculto): levanta el servidor si no
  está corriendo y abre la app en Chrome en modo app. Re-ejecutar este script
  simplemente regenera el acceso directo.
#>

$ErrorActionPreference = 'Stop'
$root    = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Global Position.lnk'

$chrome = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'(default)'
if (-not $chrome -or -not (Test-Path $chrome)) {
    $chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
}

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath       = 'powershell.exe'
$lnk.Arguments        = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$root\launch-app.ps1`""
$lnk.WorkingDirectory = $root
$lnk.Description      = 'Global Position — cartera de inversión'
if (Test-Path $chrome) { $lnk.IconLocation = "$chrome,0" }
$lnk.Save()

Write-Output "Acceso directo creado: $lnkPath"
