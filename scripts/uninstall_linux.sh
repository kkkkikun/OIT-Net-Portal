#!/usr/bin/env bash
# OIT 校园网自动登录 — Linux 卸载
# 用法：bash scripts/uninstall_linux.sh
# 默认保留配置/凭据/日志；加 --purge 一并删除 ~/.config/oit-portal
set -u

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "==> 停止 daemon 与 systemd 服务"
oit-portal stop 2>/dev/null || true
if systemctl list-unit-files 2>/dev/null | grep -q '^oit-portal\.service'; then
  $SUDO systemctl disable --now oit-portal.service 2>/dev/null || true
  $SUDO rm -f /etc/systemd/system/oit-portal.service
  $SUDO systemctl daemon-reload
fi

echo "==> 卸载 Python 包"
python3 -m pip uninstall -y oit-portal 2>/dev/null || true

if [ "${1:-}" = "--purge" ]; then
  echo "==> 删除配置/凭据/日志（--purge）"
  rm -rf "$HOME/.config/oit-portal"
else
  echo "已保留 ~/.config/oit-portal（配置/凭据/日志）；如需彻底删除请加 --purge 重跑"
fi
echo "卸载完成。"
