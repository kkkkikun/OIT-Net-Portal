"""Windows 托盘应用；GUI 依赖延迟导入，不影响核心 CLI。"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from typing import Callable

from .config import Config, load_config, save_account
from .daemon import DaemonEvent, run_daemon
from .log import get_logger, setup_logging
from .paths import AppPaths, resolve_paths
from .platform.windows import set_startup, startup_enabled

logger = get_logger()

_STATUS = {
    "starting": ("正在启动", "#64748b"),
    "checking": ("检测中", "#3b82f6"),
    "already_online": ("已在线", "#16a34a"),
    "logged_in": ("已连接", "#16a34a"),
    "no_network": ("无网络", "#64748b"),
    "need_credentials": ("需要账号密码", "#d97706"),
    "captcha_required": ("需要人工登录", "#d97706"),
    "login_rejected": ("账号或密码错误", "#dc2626"),
    "failed": ("登录失败", "#dc2626"),
    "error": ("运行异常", "#dc2626"),
    "paused": ("已暂停", "#64748b"),
}


@dataclass(frozen=True)
class TraySnapshot:
    state: str
    title: str
    detail: str
    color: str
    running: bool


class TrayController:
    def __init__(self, cfg: Config, paths: AppPaths, *,
                 runner: Callable = run_daemon):
        self.cfg = cfg
        self.paths = paths
        self._runner = runner
        self._lock = threading.RLock()
        self._stop: threading.Event | None = None
        self._wake: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._desired_running = False
        self._state = "paused"
        self._detail = "自动登录已暂停"
        self._listeners: list[Callable[[TraySnapshot], None]] = []

    def snapshot(self) -> TraySnapshot:
        with self._lock:
            title, color = _STATUS.get(self._state, _STATUS["error"])
            return TraySnapshot(self._state, title, self._detail, color,
                                self._desired_running)

    def add_listener(self, listener: Callable[[TraySnapshot], None]) -> None:
        self._listeners.append(listener)
        listener(self.snapshot())

    def _set_state(self, state: str, detail: str) -> None:
        with self._lock:
            self._state = state
            self._detail = detail
            snapshot = self.snapshot()
        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception:  # noqa: BLE001
                logger.exception("托盘状态监听器异常")

    def _on_update(self, event: DaemonEvent) -> None:
        with self._lock:
            if not self._desired_running:
                return
        self._set_state(event.state, event.detail)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop = threading.Event()
            self._wake = threading.Event()
            self._desired_running = True
            self._thread = threading.Thread(
                target=self._run,
                args=(self.cfg, self._stop, self._wake),
                name="oit-portal-tray-daemon",
                daemon=True,
            )
            self._set_state("starting", "自动登录正在启动")
            self._thread.start()

    def _run(self, cfg: Config, stop: threading.Event,
             wake: threading.Event) -> None:
        try:
            self._runner(cfg, self.paths, stop_event=stop,
                         wake_event=wake, on_update=self._on_update)
        except Exception as exc:  # noqa: BLE001
            logger.exception("托盘守护线程异常")
            self._set_state("error", f"守护线程异常：{type(exc).__name__}")
        finally:
            with self._lock:
                if self._stop is stop:
                    self._desired_running = False

    def stop(self, *, wait: bool = True) -> bool:
        with self._lock:
            self._desired_running = False
            stop = self._stop
            thread = self._thread
        if stop is not None:
            stop.set()
        if wait and thread is not None and thread is not threading.current_thread():
            thread.join(timeout=20)
            if thread.is_alive():
                self._set_state("error", "后台登录尚未停止，请稍后重试")
                return False
        self._set_state("paused", "自动登录已暂停")
        return True

    def reconnect(self) -> None:
        with self._lock:
            wake = self._wake
            running = self._thread is not None and self._thread.is_alive()
        if running and wake is not None:
            self._set_state("checking", "已请求立即重新检测")
            wake.set()
        else:
            self.start()

    def save_account(self, username: str, password: str) -> None:
        save_account(self.paths.config, self.paths.credentials, username, password)
        cfg = load_config(self.paths.config, self.paths.credentials)
        if not self.stop():
            raise RuntimeError("新设置已保存，但旧后台任务尚未停止")
        self.cfg = cfg
        self.start()


class TrayApplication:
    def __init__(self, cfg: Config, paths: AppPaths):
        import tkinter as tk

        self.cfg = cfg
        self.paths = paths
        self.controller = TrayController(cfg, paths)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("OIT 校园网")
        self.icon = None
        self._settings_window = None
        self._closing = False
        self.controller.add_listener(self._state_changed)

    def _state_changed(self, snapshot: TraySnapshot) -> None:
        if self.icon is None:
            return
        self.icon.icon = self._make_image(snapshot.color)
        self.icon.title = f"OIT 校园网 - {snapshot.title}"[:127]
        self.icon.update_menu()

    @staticmethod
    def _make_image(color: str):
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (30, 64, 175, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((5, 5, 59, 59), fill=color)
        draw.arc((15, 14, 49, 43), 205, 335, fill="white", width=4)
        draw.arc((22, 22, 42, 40), 205, 335, fill="white", width=4)
        draw.ellipse((29, 34, 35, 40), fill="white")
        return image

    def _menu_label(self, _item=None) -> str:
        snapshot = self.controller.snapshot()
        return f"状态：{snapshot.title}"

    def _detail_label(self, _item=None) -> str:
        detail = self.controller.snapshot().detail.replace("\n", " ")
        return detail[:80] if detail else "暂无详细信息"

    def _toggle_label(self, _item=None) -> str:
        return "暂停自动登录" if self.controller.snapshot().running else "启动自动登录"

    def _startup_checked(self, _item=None) -> bool:
        try:
            return startup_enabled()
        except OSError:
            return False

    def _build_icon(self):
        import pystray

        snapshot = self.controller.snapshot()
        menu = pystray.Menu(
            pystray.MenuItem(self._menu_label, None, enabled=False),
            pystray.MenuItem(self._detail_label, None, enabled=False),
            pystray.MenuItem("立即重新连接", self._reconnect),
            pystray.MenuItem(self._toggle_label, self._toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("账号设置…", self._settings),
            pystray.MenuItem("开机自动启动", self._toggle_startup,
                             checked=self._startup_checked),
            pystray.MenuItem("打开日志文件夹", self._open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._exit),
        )
        return pystray.Icon("oit-portal", self._make_image(snapshot.color),
                            "OIT 校园网", menu)

    def _on_ui(self, callback: Callable) -> None:
        if not self._closing:
            self.root.after(0, callback)

    def _reconnect(self, _icon=None, _item=None) -> None:
        self.controller.reconnect()

    def _toggle(self, _icon=None, _item=None) -> None:
        if self.controller.snapshot().running:
            self.controller.stop()
        else:
            self.controller.start()

    def _settings(self, _icon=None, _item=None) -> None:
        self._on_ui(self.show_settings)

    def _toggle_startup(self, _icon=None, _item=None) -> None:
        try:
            set_startup(not startup_enabled())
        except OSError as exc:
            self._on_ui(lambda: self._show_error("开机自启设置失败", str(exc)))
        if self.icon is not None:
            self.icon.update_menu()

    def _open_logs(self, _icon=None, _item=None) -> None:
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.paths.log_dir)  # type: ignore[attr-defined]
        else:
            logger.info("日志目录：%s", self.paths.log_dir)

    def _exit(self, _icon=None, _item=None) -> None:
        self._on_ui(self.close)

    def _show_error(self, title: str, message: str) -> None:
        from tkinter import messagebox
        messagebox.showerror(title, message, parent=self._settings_window)

    def show_settings(self) -> None:
        import tkinter as tk
        from tkinter import messagebox

        if self._settings_window is not None:
            self._settings_window.deiconify()
            self._settings_window.lift()
            return
        window = tk.Toplevel(self.root)
        self._settings_window = window
        window.title("OIT 校园网 - 账号设置")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        frame = tk.Frame(window, padx=20, pady=18)
        frame.pack()
        tk.Label(frame, text="校园网账号").grid(row=0, column=0, sticky="w", pady=5)
        username = tk.Entry(frame, width=30)
        username.grid(row=0, column=1, pady=5)
        username.insert(0, self.controller.cfg.username or "")
        tk.Label(frame, text="校园网密码").grid(row=1, column=0, sticky="w", pady=5)
        password = tk.Entry(frame, width=30, show="●")
        password.grid(row=1, column=1, pady=5)
        tk.Label(frame, text="密码仅保存在本机独立的凭据文件中",
                 fg="#64748b").grid(row=2, column=0, columnspan=2, pady=(2, 12))

        def save() -> None:
            try:
                self.controller.save_account(username.get(), password.get())
            except (ValueError, OSError, RuntimeError) as exc:
                messagebox.showerror("无法保存设置", str(exc), parent=window)
                return
            self.cfg = self.controller.cfg
            password.delete(0, tk.END)
            window.withdraw()

        tk.Button(frame, text="保存并连接", command=save,
                  width=14).grid(row=3, column=0, columnspan=2)
        window.bind("<Return>", lambda _event: save())
        username.focus_set()
        window.deiconify()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.controller.stop(wait=False)
        if self.icon is not None:
            self.icon.stop()
        self.root.after(100, self.root.destroy)

    def run(self) -> int:
        self.icon = self._build_icon()
        self.icon.run_detached()
        if self.cfg.username and self.cfg.password:
            self.controller.start()
        else:
            self.root.after(100, self.show_settings)
        self.root.mainloop()
        return 0


def main() -> int:
    paths = resolve_paths()
    setup_logging(paths.log_file, console=False)
    try:
        cfg = load_config(paths.config, paths.credentials)
        app = TrayApplication(cfg, paths)
        return app.run()
    except ImportError as exc:
        print(f"托盘依赖未安装，请执行 pip install .[tray]：{exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"无法启动托盘应用：{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
