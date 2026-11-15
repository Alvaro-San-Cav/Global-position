"""Actualización en segundo plano para LifeDeck: tarea programada y script sin ventana."""
import subprocess
from datetime import datetime

import pytest

import lifedeck_job
from src import lifedeck, lifedeck_auto


def test_task_xml_has_interval_paths_and_battery_settings():
    xml = lifedeck_auto.task_xml(30, r"C:\venv\Scripts\pythonw.exe", r"C:\gp\backend\lifedeck_job.py",
                                 r"C:\gp\backend", start=datetime(2026, 11, 16, 10, 0, 0))
    assert "<Interval>PT30M</Interval>" in xml
    assert "<StartBoundary>2026-11-16T10:00:00</StartBoundary>" in xml
    assert r"<Command>C:\venv\Scripts\pythonw.exe</Command>" in xml
    assert r'<Arguments>"C:\gp\backend\lifedeck_job.py"</Arguments>' in xml
    assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml


def test_task_xml_rejects_odd_interval():
    with pytest.raises(lifedeck_auto.AutoError):
        lifedeck_auto.task_xml(7, "python.exe")


def test_task_xml_escapes_paths():
    xml = lifedeck_auto.task_xml(15, r"C:\A&B\pythonw.exe")
    assert r"C:\A&amp;B\pythonw.exe" in xml


def test_pythonw_path_prefers_pythonw(tmp_path):
    exe = tmp_path / "python.exe"
    exe.write_text("")
    assert lifedeck_auto.pythonw_path(str(exe)) == str(exe)
    (tmp_path / "pythonw.exe").write_text("")
    assert lifedeck_auto.pythonw_path(str(exe)) == str(tmp_path / "pythonw.exe")


def test_install_creates_from_xml_and_runs(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(lifedeck_auto, "supported", lambda: True)
    monkeypatch.setattr(lifedeck_auto, "_schtasks", fake)
    lifedeck_auto.install(30)
    assert calls[0][:5] == ("/Create", "/F", "/TN", lifedeck_auto.TASK_NAME, "/XML")
    assert calls[1] == ("/Run", "/TN", lifedeck_auto.TASK_NAME)


def test_install_reports_schtasks_error(monkeypatch):
    monkeypatch.setattr(lifedeck_auto, "supported", lambda: True)
    monkeypatch.setattr(lifedeck_auto, "_schtasks",
                        lambda *a: subprocess.CompletedProcess(a, 1, "", "ERROR: Acceso denegado.\n"))
    with pytest.raises(lifedeck_auto.AutoError, match="Acceso denegado"):
        lifedeck_auto.install(30)


def test_job_pushes_fresh_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    lifedeck.save_settings({"url": "https://example.test", "token": "t"})
    pushed, builds = [], []
    monkeypatch.setattr(lifedeck, "push", lambda d: pushed.append(d))

    def build(force_refresh):
        builds.append(force_refresh)
        return {"net_worth": 1}

    assert lifedeck_job.run(build) == 0
    assert builds == [True] and pushed == [{"net_worth": 1}]
    s = lifedeck.load_settings()
    assert s["last_auto_at"] and s["last_auto_error"] == ""


def test_job_records_error(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    lifedeck.save_settings({"url": "https://example.test", "token": "t"})
    assert lifedeck_job.run(lambda force_refresh: {"error": "Sin operaciones"}) == 1
    assert lifedeck.load_settings()["last_auto_error"] == "Sin operaciones"


def test_job_skips_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    assert lifedeck_job.run(lambda force_refresh: pytest.fail("no debe calcular")) == 0
    assert "Falta" in lifedeck.load_settings()["last_auto_error"]
