from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = (ROOT / "scripts/install_linux.sh").read_text(encoding="utf-8")
UNINSTALL = (ROOT / "scripts/uninstall_linux.sh").read_text(encoding="utf-8")
BUILD = (ROOT / "scripts/build_linux.sh").read_text(encoding="utf-8")
SERVICE = (ROOT / "scripts/oit-portal.service.template").read_text(encoding="utf-8")


def test_installer_uses_isolated_venv_and_offline_wheelhouse():
    assert '"$VENV_DIR/bin/python" -m pip install' in INSTALL
    assert '--no-index --find-links="$PACKAGE_DIR/wheelhouse"' in INSTALL
    assert 'OIT_PORTAL_HOME="$CFG_DIR" "$EXEC_START" configure' in INSTALL
    assert 'read -rsp' not in INSTALL
    assert 'printf \'password' not in INSTALL
    assert 'ln -sfn "$EXEC_START" "$BIN_LINK"' in INSTALL


def test_installer_is_repeatable_and_never_runs_as_root():
    assert '[ "$(id -u)" -ne 0 ]' in INSTALL
    assert "--skip-login" in INSTALL
    assert "systemctl enable --now oit-portal.service" in INSTALL
    assert 'systemctl restart oit-portal.service' in INSTALL
    assert 'if [ ! -f "$CFG_DIR/config.toml" ]' in INSTALL


def test_service_uses_explicit_paths_and_config_home():
    assert "ExecStart=@EXEC_START@ daemon" in SERVICE
    assert "User=@USER@" in SERVICE
    assert "Environment=OIT_PORTAL_HOME=@CONFIG_HOME@" in SERVICE
    assert "\nPrivateTmp=" not in SERVICE
    assert "\nProtectHome=" not in SERVICE


def test_uninstaller_preserves_config_unless_purge():
    assert 'rm -rf "$DATA_DIR"' in UNINSTALL
    assert 'if [ "${1:-}" = "--purge" ]' in UNINSTALL
    assert 'rm -rf "$CFG_DIR"' in UNINSTALL
    assert '[ "$(id -u)" -ne 0 ]' in UNINSTALL


def test_build_bundle_contains_only_runtime_installation_files():
    assert 'python3 -m pip wheel --timeout 60 --wheel-dir "$PKG_DIR/wheelhouse" "$ROOT"' in BUILD
    for name in (
        "install.sh", "uninstall.sh", "oit-portal.service.template",
        "config.example.toml", "README.md", "BUILD-INFO",
    ):
        assert name in BUILD
    assert 'sha256sum "$PACKAGE.tar.gz"' in BUILD
    assert "credentials" not in BUILD
    assert "session.json" not in BUILD
