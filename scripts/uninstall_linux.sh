#!/usr/bin/env bash
# OIT 校园网自动登录 — Linux 卸载；默认保留配置，--purge 全部删除
set -euo pipefail

case "${1:-}" in
  ""|--purge) ;;
  *) echo "用法：bash uninstall_linux.sh [--purge]" >&2; exit 2 ;;
esac
[ "$(id -u)" -ne 0 ] || { echo "错误：请以原安装用户运行，不要使用 root" >&2; exit 1; }

SUDO="sudo"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/oit-portal"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/oit-portal"
EXEC_START="$DATA_DIR/venv/bin/oit-portal"

echo "==> 停止 daemon 与 systemd 服务"
if [ -x "$EXEC_START" ]; then
  "$EXEC_START" stop 2>/dev/null || true
fi
if [ -f /etc/systemd/system/oit-portal.service ]; then
  $SUDO systemctl disable --now oit-portal.service 2>/dev/null || true
  $SUDO rm -f /etc/systemd/system/oit-portal.service
  $SUDO systemctl daemon-reload
fi

echo "==> 删除应用与命令入口"
rm -rf "$DATA_DIR"
rm -f "$HOME/.local/bin/oit-portal"
if command -v python3 >/dev/null; then
  python3 -m pip uninstall -y oit-portal 2>/dev/null || true
fi

if [ "${1:-}" = "--purge" ]; then
  echo "==> 删除配置、凭据、会话与日志"
  rm -rf "$CFG_DIR"
else
  echo "已保留 $CFG_DIR（如需彻底删除请使用 --purge）"
fi
echo "卸载完成。"
