from __future__ import annotations

import threading
import time

from oit_portal.auth.flow import FlowResult, FlowOutcome
from oit_portal.daemon import SingleInstanceLock, _wait_for_next_run, run_daemon
from oit_portal.paths import AppPaths


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


def test_run_daemon_emits_events_and_always_cleans_up(cfg, tmp_path, monkeypatch):
    paths = make_paths(tmp_path)
    stop = threading.Event()
    events = []

    class Flow:
        def __init__(self, *_args, **_kwargs):
            pass

        def ensure_online(self, *, allow_password):
            return FlowResult(FlowOutcome.ALREADY_ONLINE, "online")

    monkeypatch.setattr("oit_portal.daemon.AuthFlow", Flow)

    def on_update(event):
        events.append(event)
        if event.outcome is FlowOutcome.ALREADY_ONLINE:
            stop.set()

    assert run_daemon(cfg, paths, stop_event=stop, on_update=on_update) == 0
    assert [event.state for event in events] == ["checking", "already_online"]
    assert not paths.pid.exists()
    lock = SingleInstanceLock(paths.lock)
    assert lock.acquire()
    lock.release()


def test_wait_for_next_run_can_be_woken_without_stopping():
    stop = threading.Event()
    wake = threading.Event()
    timer = threading.Timer(0.03, wake.set)
    timer.start()
    started = time.monotonic()

    _wait_for_next_run(stop, wake, 10)

    assert time.monotonic() - started < 1
    assert not stop.is_set()
    assert not wake.is_set()
