' launch-app.vbs — arranca Global Position sin mostrar NINGUNA consola.
'
' wscript.exe es una app GUI: al contrario que powershell.exe lanzado desde un
' acceso directo, no crea ventana de consola ni siquiera un instante. Este
' wrapper ejecuta launch-app.ps1 totalmente oculto (estilo 0).
' El acceso directo del escritorio apunta aquí (ver create-desktop-shortcut.ps1).

Dim fso, shell, root
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)

shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & root & "\launch-app.ps1""", 0, False
