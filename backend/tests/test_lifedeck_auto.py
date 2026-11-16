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


# ── reintentos y avisos del job ────────────────────────────────────────────────
@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    lifedeck.save_settings({"url": "https://example.test", "token": "t"})


def test_job_retries_transient_push_error(configured, monkeypatch):
    calls, sleeps = [], []

    def push(d):
        calls.append(d)
        if len(calls) == 1:
            raise lifedeck.LifeDeckError("No se pudo conectar con LifeDeck: getaddrinfo failed", transient=True)
        return {"ok": True, "as_of": "2026-11-16", "prices_as_of": "2026-11-16"}

    monkeypatch.setattr(lifedeck, "push", push)
    rc = lifedeck_job.run(lambda force_refresh: {"net_worth": 1}, sleep=sleeps.append,
                          today=datetime(2026, 11, 16).date())
    assert rc == 0 and len(calls) == 2 and sleeps == [lifedeck_job.RETRY_DELAY]
    assert lifedeck.load_settings()["last_auto_error"] == ""


def test_job_gives_up_after_attempts(configured, monkeypatch):
    def push(d):
        raise lifedeck.LifeDeckError("sin red", transient=True)

    monkeypatch.setattr(lifedeck, "push", push)
    sleeps = []
    assert lifedeck_job.run(lambda force_refresh: {"net_worth": 1}, sleep=sleeps.append) == 1
    assert len(sleeps) == lifedeck_job.ATTEMPTS - 1
    assert lifedeck.load_settings()["last_auto_error"] == "sin red"


def test_job_does_not_retry_permanent_error(configured, monkeypatch):
    def push(d):
        raise lifedeck.LifeDeckError("Token no válido.")

    monkeypatch.setattr(lifedeck, "push", push)
    sleeps = []
    assert lifedeck_job.run(lambda force_refresh: {"net_worth": 1}, sleep=sleeps.append) == 1
    assert sleeps == []


def test_job_retries_when_no_new_prices_then_warns(configured, monkeypatch):
    pushed, sleeps = [], []
    monkeypatch.setattr(lifedeck, "push", lambda d: pushed.append(d) or {"prices_as_of": "2026-11-16"})
    rc = lifedeck_job.run(lambda force_refresh: {"net_worth": 1}, sleep=sleeps.append,
                          prices_stamp=lambda: 123.0, today=datetime(2026, 11, 16).date())
    assert rc == 0
    assert len(sleeps) == lifedeck_job.ATTEMPTS - 1 and len(pushed) == 1
    assert "precios nuevos" in lifedeck.load_settings()["last_auto_error"]


def test_job_no_retry_when_prices_downloaded(configured, monkeypatch):
    stamps = iter([1.0, 2.0])
    monkeypatch.setattr(lifedeck, "push", lambda d: {"prices_as_of": "2026-11-16"})
    sleeps = []
    assert lifedeck_job.run(lambda force_refresh: {"net_worth": 1}, sleep=sleeps.append,
                            prices_stamp=lambda: next(stamps), today=datetime(2026, 11, 16).date()) == 0
    assert sleeps == [] and lifedeck.load_settings()["last_auto_error"] == ""


def test_job_warns_on_old_prices(configured, monkeypatch):
    monkeypatch.setattr(lifedeck, "push", lambda d: {"prices_as_of": "2026-11-05"})
    assert lifedeck_job.run(lambda force_refresh: {"net_worth": 1}, today=datetime(2026, 11, 16).date()) == 0
    assert "05/11" in lifedeck.load_settings()["last_auto_error"]


def test_job_weekend_prices_are_not_stale():
    assert lifedeck_job._stale_warning("2026-11-13", datetime(2026, 11, 16).date()) == ""  # viernes -> lunes


def test_job_does_not_write_when_settings_unreadable(tmp_path, monkeypatch):
    path = tmp_path / "lifedeck.json"
    path.write_text("{roto", encoding="utf-8")
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(path))
    assert lifedeck_job.run(lambda force_refresh: pytest.fail("no debe calcular")) == 1
    assert path.read_text(encoding="utf-8") == "{roto"


def test_job_survives_failing_status_write(configured, monkeypatch):
    monkeypatch.setattr(lifedeck, "push", lambda d: {"ok": True})

    def fail(patch):
        raise PermissionError("busy")

    monkeypatch.setattr(lifedeck, "save_settings", fail)
    assert lifedeck_job.run(lambda force_refresh: {"net_worth": 1}) == 0


# ── estado de la tarea ─────────────────────────────────────────────────────────
def test_parse_status_detects_missing_python(tmp_path):
    script = tmp_path / "job & co.py"
    script.write_text("")
    py = tmp_path / "pythonw.exe"
    py.write_text("")
    ok = lifedeck_auto.task_xml(30, str(py), str(script), str(tmp_path))
    assert lifedeck_auto.parse_status(ok) == {"command": str(py), "script": str(script), "broken": False}
    gone = lifedeck_auto.task_xml(30, str(tmp_path / "old-venv" / "pythonw.exe"), str(script), str(tmp_path))
    assert lifedeck_auto.parse_status(gone)["broken"] is True


def test_status_is_cached_and_invalidated_on_install(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1 if args[0] == "/Query" else 0, "", "")

    monkeypatch.setattr(lifedeck_auto, "supported", lambda: True)
    monkeypatch.setattr(lifedeck_auto, "_schtasks", fake)
    lifedeck_auto._invalidate_status()
    assert lifedeck_auto.is_installed() is False
    assert lifedeck_auto.is_installed() is False
    assert sum(1 for c in calls if c[0] == "/Query") == 1
    lifedeck_auto.install(30)
    lifedeck_auto.is_installed()
    assert sum(1 for c in calls if c[0] == "/Query") == 2
    lifedeck_auto._invalidate_status()


# ── rutas /api/lifedeck* ───────────────────────────────────────────────────────
@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import server

    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    monkeypatch.setattr(lifedeck_auto, "status", lambda force=False: {"installed": False, "broken": False})
    return TestClient(server.app)


def test_route_auto_requires_token(api):
    r = api.post("/api/lifedeck/auto", json={"enabled": True, "minutes": 30})
    assert r.status_code == 409


def test_route_auto_rejects_bad_interval(api):
    lifedeck.save_settings({"url": "https://example.test", "token": "t"})
    assert api.post("/api/lifedeck/auto", json={"enabled": True, "minutes": 7}).status_code == 400
    assert api.post("/api/lifedeck/auto", json={"enabled": "yes"}).status_code == 400


def test_route_auto_reports_schtasks_failure(api, monkeypatch):
    lifedeck.save_settings({"url": "https://example.test", "token": "t"})

    def boom(minutes, run_now=True):
        raise lifedeck_auto.AutoError("No se pudo crear la tarea programada: Acceso denegado.")

    monkeypatch.setattr(lifedeck_auto, "install", boom)
    r = api.post("/api/lifedeck/auto", json={"enabled": True, "minutes": 60})
    assert r.status_code == 502 and "Acceso denegado" in r.json()["message"]


def test_route_auto_installs_and_saves_interval(api, monkeypatch):
    lifedeck.save_settings({"url": "https://example.test", "token": "t"})
    installed = []
    monkeypatch.setattr(lifedeck_auto, "install", lambda minutes, run_now=True: installed.append(minutes))
    r = api.post("/api/lifedeck/auto", json={"enabled": True, "minutes": 60})
    assert r.status_code == 200 and installed == [60] and r.json()["auto_minutes"] == 60
    assert "auto_broken" in r.json() and "token" not in r.json()


def test_route_post_only_patches_given_fields(api):
    lifedeck.save_settings({"url": "https://example.test", "token": "t", "enabled": False})
    r = api.post("/api/lifedeck", json={"enabled": True})
    assert r.status_code == 200 and r.json()["enabled"] is True
    s = lifedeck.load_settings()
    assert s["url"] == "https://example.test" and s["token"] == "t"
    assert api.post("/api/lifedeck", json={"url": "ftp://x"}).status_code == 400
