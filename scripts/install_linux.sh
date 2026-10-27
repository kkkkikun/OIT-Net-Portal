#!/usr/bin/env bash
# OIT 校园网自动登录 — Linux 离线包/源码一键安装
set -euo pipefail

SKIP_LOGIN=false
case "${1:-}" in
  "" ) ;;
  --skip-login) SKIP_LOGIN=true ;;
  -h|--help)
    echo "用法：bash install_linux.sh [--skip-login]"
    exit 0
    ;;
  *) echo "错误：未知参数 $1" >&2; exit 2 ;;
esac

err() { echo "错误：$*" >&2; exit 1; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/wheelhouse" ]; then
  PACKAGE_DIR="$SCRIPT_DIR"
  PROJECT_ROOT=""
else
  PACKAGE_DIR=""
  PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
fi
CONFIG_TEMPLATE="${PACKAGE_DIR:-$PROJECT_ROOT}/config.example.toml"
SERVICE_TEMPLATE="${PACKAGE_DIR:-$PROJECT_ROOT/scripts}/oit-portal.service.template"
[ -f "$CONFIG_TEMPLATE" ] || err "安装包缺少 config.example.toml"
[ -f "$SERVICE_TEMPLATE" ] || err "安装包缺少 oit-portal.service.template"

command -v systemctl >/dev/null || err "需要 systemd（本安装器仅支持 systemd Linux）"
[ -z "${TERMUX_VERSION:-}" ] || err "检测到 Termux，请改用 scripts/install_termux.sh"
[ "$(id -u)" -ne 0 ] || err "请勿以 root 运行；请以使用校园网的普通用户执行，脚本仅在写 systemd 服务时调用 sudo"
command -v sudo >/dev/null || err "安装系统服务需要 sudo"
command -v python3 >/dev/null || err "未找到 python3；Ubuntu/Debian 可先执行：sudo apt install python3 python3-venv"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)' \
  || err "需要 Python >= 3.9（当前 $(python3 -V 2>&1)）"
if [ -n "$PACKAGE_DIR" ]; then
  EXPECTED_PYTHON="$(python3 -c 'import sys; from pathlib import Path; lines=Path(sys.argv[1]).read_text().splitlines(); print(next(x.split("=",1)[1] for x in lines if x.startswith("build_python=")))' "$PACKAGE_DIR/BUILD-INFO")"
  EXPECTED_PYTHON="${EXPECTED_PYTHON%.*}"
  CURRENT_PYTHON="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
  [ "$EXPECTED_PYTHON" = "$CURRENT_PYTHON" ] \
    || err "此离线包按 Python $EXPECTED_PYTHON 构建，当前为 $CURRENT_PYTHON；请使用匹配版本或从源码安装"
fi

CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/oit-portal"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/oit-portal"
VENV_DIR="$DATA_DIR/venv"
EXEC_START="$VENV_DIR/bin/oit-portal"
BIN_LINK="$HOME/.local/bin/oit-portal"
UNIT_TMP=""

cleanup() {
  [ -z "$UNIT_TMP" ] || rm -f "$UNIT_TMP"
}
trap cleanup EXIT

echo "==> [1/6] 准备用户目录与 Python 环境"
mkdir -p "$CFG_DIR/logs" "$DATA_DIR" "$HOME/.local/bin"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR" 2>/dev/null \
    || err "无法创建 venv；Ubuntu/Debian 请执行：sudo apt install python3-venv"
fi

echo "==> [2/6] 安装 oit-portal 与依赖"
if [ -n "$PACKAGE_DIR" ]; then
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade \
    --no-index --find-links="$PACKAGE_DIR/wheelhouse" oit-portal
  echo "    已使用安装包内依赖（无需联网）"
else
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade "$PROJECT_ROOT"
fi
[ -x "$EXEC_START" ] || err "安装后未找到 $EXEC_START"
ln -sfn "$EXEC_START" "$BIN_LINK"

echo "==> [3/6] 配置校园网账号"
if [ ! -f "$CFG_DIR/config.toml" ]; then
  cp "$CONFIG_TEMPLATE" "$CFG_DIR/config.toml"
fi
OIT_PORTAL_HOME="$CFG_DIR" "$EXEC_START" configure

echo "==> [4/6] 注册 systemd 系统服务"
"$EXEC_START" stop 2>/dev/null || true
UNIT_TMP="$(mktemp)"
TEMPLATE="$SERVICE_TEMPLATE" OUTPUT="$UNIT_TMP" TARGET_USER="$(id -un)" \
  TARGET_HOME="$HOME" TARGET_EXEC="$EXEC_START" TARGET_CONFIG="$CFG_DIR" \
  "$VENV_DIR/bin/python" - <<'PY'
import os
from pathlib import Path

text = Path(os.environ["TEMPLATE"]).read_text(encoding="utf-8")
for key, value in {
    "@USER@": os.environ["TARGET_USER"],
    "@HOME@": os.environ["TARGET_HOME"],
    "@EXEC_START@": os.environ["TARGET_EXEC"],
    "@CONFIG_HOME@": os.environ["TARGET_CONFIG"],
}.items():
    text = text.replace(key, value)
Path(os.environ["OUTPUT"]).write_text(text, encoding="utf-8")
PY
sudo install -m 644 "$UNIT_TMP" /etc/systemd/system/oit-portal.service
sudo systemctl daemon-reload
sudo systemctl enable --now oit-portal.service
sudo systemctl restart oit-portal.service

echo "==> [5/6] 检查服务"
systemctl --no-pager --full status oit-portal.service || true

if [ "$SKIP_LOGIN" = false ]; then
  echo "==> [6/6] 试跑登录（非校园网或需验证码时可稍后重试）"
  "$EXEC_START" once || true
else
  echo "==> [6/6] 已跳过安装后试登"
fi

cat <<TIP

安装完成：systemd 服务已设置为开机自启。
命令入口：$BIN_LINK（如找不到，请把 ~/.local/bin 加入 PATH）

常用操作：
  oit-portal status                 查看网络状态
  oit-portal configure              修改账号密码
  sudo systemctl restart oit-portal 修改配置后重启服务
  systemctl status oit-portal       查看服务状态
  journalctl -u oit-portal -f       实时日志

配置文件：$CFG_DIR/config.toml
日志文件：$CFG_DIR/logs/oit-portal.log
TIP
