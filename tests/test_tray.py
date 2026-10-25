from __future__ import annotations

import threading
import time

from oit_portal.daemon import DaemonEvent
from oit_portal.paths import AppPaths
from oit_portal.platform.windows import startup_command
from oit_portal.tray import TrayController


def make_paths(tmp_path):
    return AppPaths(
        home=tmp_path,
        config=tmp_path / "config.toml",
        credentials=tmp_path / "credentials.toml",
        session=tmp_path / "session.json",
        log_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "oit-portal.log",
        lock=tmp_path / "app.lock",
        pid=tmp_path / "app.pid",
    )


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_controller_reconnect_wakes_same_daemon(cfg, tmp_path):
    started = threading.Event()
    woke = threading.Event()
    thread_ids = []

    def runner(_cfg, _paths, *, stop_event, wake_event, on_update):
        thread_ids.append(threading.get_ident())
        started.set()
        on_update(DaemonEvent("checking"))
        while not stop_event.is_set():
            if wake_event.wait(0.02):
                wake_event.clear()
                woke.set()
                on_update(DaemonEvent("already_online", "online"))

    controller = TrayController(cfg, make_paths(tmp_path), runner=runner)
    controller.start()
    assert started.wait(1)
    controller.reconnect()
    assert woke.wait(1)
    assert wait_until(lambda: controller.snapshot().state == "already_online")
    assert controller.stop()
    assert len(thread_ids) == 1
    assert not controller.snapshot().running


def test_controller_pause_resume_and_status_listeners(cfg, tmp_path):
    calls = []

    def runner(_cfg, _paths, *, stop_event, **_kwargs):
        stop_event.wait(1)
        calls.append("stopped")

    controller = TrayController(cfg, make_paths(tmp_path), runner=runner)
    snapshots = []
    controller.add_listener(snapshots.append)
    assert controller.snapshot().state == "paused"
    controller.start()
    controller._on_update(DaemonEvent("no_network", "offline"))
    assert controller.snapshot().title == "无网络"
    assert controller.stop()
    controller.start()
    assert controller.stop()
    assert calls == ["stopped", "stopped"]
    assert snapshots[-1].state == "paused"


def test_first_saved_account_starts_connection(cfg, tmp_path):
    configs = []

    def runner(current_cfg, _paths, *, stop_event, **_kwargs):
        configs.append(current_cfg.username)
        stop_event.wait(1)

    controller = TrayController(cfg, make_paths(tmp_path), runner=runner)
    controller.save_account("first-user", "first-password")
    assert wait_until(lambda: configs == ["first-user"])
    assert controller.snapshot().running
    assert controller.stop()


def test_save_account_restarts_with_new_config(cfg, tmp_path):
    configs = []

    def runner(current_cfg, _paths, *, stop_event, **_kwargs):
        configs.append(current_cfg.username)
        stop_event.wait(1)

    paths = make_paths(tmp_path)
    controller = TrayController(cfg, paths, runner=runner)
    controller.start()
    controller.save_account("new-user", "new-password")
    assert wait_until(lambda: configs == [cfg.username, "new-user"])
    assert controller.stop()
    assert controller.cfg.password == "new-password"


def test_windows_startup_command_quotes_executable():
    command = startup_command(r"C:\Program Files\OIT\OIT-Portal.exe")
    assert command == r'"C:\Program Files\OIT\OIT-Portal.exe"'
