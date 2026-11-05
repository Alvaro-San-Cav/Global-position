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

$icon = Join-Path $root 'frontend\public\app-icon.ico'

# wscript (GUI) evita el parpadeo de consola que produce powershell.exe
# lanzado directamente desde un .lnk, incluso con -WindowStyle Hidden.
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath       = "$env:SystemRoot\System32\wscript.exe"
$lnk.Arguments        = "`"$root\launch-app.vbs`""
$lnk.WorkingDirectory = $root
$lnk.Description      = 'Global Position — cartera de inversión'
if (Test-Path $icon) { $lnk.IconLocation = "$icon,0" }
$lnk.Save()

Write-Output "Acceso directo creado: $lnkPath"
