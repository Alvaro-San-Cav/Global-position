"""
Actualización en segundo plano para LifeDeck, sin tener Global Position abierto.

Crea (o borra) una tarea del Programador de tareas de Windows, a nivel de usuario (sin admin),
que cada N minutos ejecuta `lifedeck_job.py` con pythonw (sin ventana): recalcula el panel con
precios frescos de Yahoo y sube el resumen a LifeDeck.

La tarea se define en XML para poder:
  - ejecutarse también con portátil en batería,
  - no lanzar otra si la anterior sigue corriendo,
  - recuperar la ejecución perdida si el PC estaba suspendido (StartWhenAvailable),
  - cortarla si se cuelga (20 min).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from xml.sax.saxutils import escape, unescape

TASK_NAME = "GlobalPosition LifeDeck"
INTERVALS = (15, 30, 60, 120)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_SCRIPT = os.path.join(BACKEND_DIR, "lifedeck_job.py")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AutoError(Exception):
    pass


def supported() -> bool:
    return sys.platform == "win32"


def pythonw_path(executable: str | None = None) -> str:
    """pythonw.exe junto al python actual (el del venv); si no existe, el mismo python."""
    exe = executable or sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def task_xml(minutes: int, python: str, script: str = JOB_SCRIPT, workdir: str = BACKEND_DIR,
             start: datetime | None = None) -> str:
    if minutes not in INTERVALS:
        raise AutoError(f"Intervalo no permitido: {minutes} min.")
    begin = (start or datetime.now()).replace(microsecond=0).isoformat()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Global Position: recalcula el patrimonio y lo sube a LifeDeck cada {minutes} min.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{begin}</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{minutes}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT20M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python)}</Command>
      <Arguments>"{escape(script)}"</Arguments>
      <WorkingDirectory>{escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks.exe", *args], capture_output=True, text=True, creationflags=_NO_WINDOW)


def _fail(res: subprocess.CompletedProcess, what: str) -> AutoError:
    detail = (res.stderr or res.stdout or "").strip().splitlines()
    return AutoError(f"No se pudo {what} la tarea programada" + (f": {detail[-1]}" if detail else "."))


_STATUS_TTL = 15.0
_status_cache: tuple[float, dict] | None = None
_status_lock = threading.Lock()


def _invalidate_status() -> None:
    global _status_cache
    with _status_lock:
        _status_cache = None


def _tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}>(.*?)</{name}>", xml, re.S)
    return unescape(m.group(1).strip()) if m else None


def parse_status(xml: str) -> dict:
    """De `schtasks /Query /XML`: ruta del Python y del script de la tarea, y si siguen existiendo.

    Si el venv se recrea o se mueve, Windows no llega a ejecutar el job (ni deja error en
    lifedeck.json): `broken` lo detecta para que la UI pida reactivar la tarea."""
    command = _tag(xml, "Command")
    args = _tag(xml, "Arguments")
    script = args.strip().strip('"') if args else None
    missing = [p for p in (command, script) if p and not os.path.exists(p)]
    return {"command": command, "script": script, "broken": bool(missing)}


def status(force: bool = False) -> dict:
    """{installed, broken}. Cacheado unos segundos: cada GET /api/lifedeck lanzaría schtasks.exe."""
    global _status_cache
    if not supported():
        return {"installed": False, "broken": False}
    now = time.monotonic()
    with _status_lock:
        if not force and _status_cache and now - _status_cache[0] < _STATUS_TTL:
            return dict(_status_cache[1])
    res = _schtasks("/Query", "/TN", TASK_NAME, "/XML")
    if res.returncode != 0:
        out = {"installed": False, "broken": False}
    else:
        info = parse_status(res.stdout or "")
        out = {"installed": True, "broken": info["broken"]}
    with _status_lock:
        _status_cache = (time.monotonic(), out)
    return dict(out)


def is_installed() -> bool:
    return status()["installed"]


def install(minutes: int, run_now: bool = True) -> None:
    if not supported():
        raise AutoError("La actualización en segundo plano solo está disponible en Windows.")
    xml = task_xml(minutes, pythonw_path())
    _invalidate_status()
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(xml)
        res = _schtasks("/Create", "/F", "/TN", TASK_NAME, "/XML", path)
        if res.returncode != 0:
            raise _fail(res, "crear")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    _invalidate_status()
    if run_now:
        _schtasks("/Run", "/TN", TASK_NAME)  # primera ejecución ya; si falla, la siguiente llegará sola


def uninstall() -> None:
    if not supported() or not status(force=True)["installed"]:
        return
    res = _schtasks("/Delete", "/F", "/TN", TASK_NAME)
    _invalidate_status()
    if res.returncode != 0:
        raise _fail(res, "borrar")
