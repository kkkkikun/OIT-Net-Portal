#!/usr/bin/env bash
# OIT 校园网自动登录 — Linux（systemd）一键安装
# 用法：以「运行 daemon 的目标普通用户」身份，在项目目录执行：
#   bash scripts/install_linux.sh
# 装包/配置/凭据写入当前用户目录；写 systemd unit 的步骤会自动调用 sudo。
set -eu

err() { echo "错误：$*" >&2; exit 1; }

# ── 0. 环境与身份检查 ──────────────────────────────────────
command -v systemctl >/dev/null || err "需要 systemd（本脚本仅支持 systemd 的 Linux）"
[ -z "${TERMUX_VERSION:-}" ] || err "检测到 Termux，请改用 scripts/install_termux.sh"
[ "$(id -u)" -ne 0 ] || err "请勿以 root 运行：daemon 将以执行本脚本的用户身份运行，
    配置/凭据也会写入该用户目录。请先 su - <目标用户> 后重跑
    （写 systemd unit 的步骤会自动调用 sudo）"
echo "==> [1/7] 检查 python3（>= 3.9）"
command -v python3 >/dev/null || err "未找到 python3，请先: sudo apt install python3 python3-pip"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)' \
  || err "需要 Python >= 3.9（当前 $(python3 -V 2>&1)）"
python3 -m pip --version >/dev/null 2>&1 || err "缺少 pip，请先: sudo apt install python3-pip"

# ── 1. 安装本项目（--user，不碰系统 site-packages，无需 sudo）──
echo "==> [2/7] 安装 oit-portal 及依赖（pip --user）"
python3 -m pip install --quiet --user .
# 三级解析 console script 绝对路径（systemd 无用户 PATH）
EXEC_START="$(command -v oit-portal || true)"
[ -n "$EXEC_START" ] || EXEC_START="$HOME/.local/bin/oit-portal"
[ -x "$EXEC_START" ] || EXEC_START="$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))')/oit-portal"
[ -x "$EXEC_START" ] || err "找不到 oit-portal 可执行文件（pip --user 安装后应在 ~/.local/bin/）"
echo "    ExecStart = $EXEC_START"

# ── 2. 配置文件 ─────────────────────────────────────────────
CFG_DIR="${HOME}/.config/oit-portal"
mkdir -p "$CFG_DIR"
echo "==> [3/7] 生成配置 $CFG_DIR"
if [ ! -f "$CFG_DIR/config.toml" ]; then
  cp "$(dirname "$0")/../config.example.toml" "$CFG_DIR/config.toml"
  echo "    已复制 config.example.toml -> config.toml"
else
  echo "    config.toml 已存在，保留"
fi

read -rp "请输入校园网账号（学号/工号，直接回车保持不变）: " USERNAME
if [ -n "$USERNAME" ]; then
  sed -i "s/^username = .*/username = \"$USERNAME\"/" "$CFG_DIR/config.toml"
fi

echo "==> [4/7] 写入凭据（密码只存本机，权限 600）"
read -rsp "请输入校园网密码（输入不回显）: " PASSWORD; echo
# 用 chmod 直接收紧权限（不用 umask 177，避免 umask 污染到
# 后续 oit-portal 子进程导致日志目录创建失败）
printf 'password = "%s"\n' "$PASSWORD" > "$CFG_DIR/credentials.toml"
chmod 600 "$CFG_DIR/credentials.toml"
unset PASSWORD

# ── 3. systemd 系统服务 ────────────────────────────────────
echo "==> [5/7] 安装 systemd 服务（需要 sudo）"
command -v sudo >/dev/null || err "安装系统服务需要 sudo（sudo apt install sudo）"
# 先停掉可能在跑的手动 daemon，避免 enable --now 撞锁后服务显示
# inactive(dead)（锁冲突是「目标已达成」，退出码 0，systemd 不会重启）
oit-portal stop 2>/dev/null || true
sed -e "s|@USER@|$(id -un)|g" \
    -e "s|@EXEC_START@|$EXEC_START|g" \
    -e "s|@HOME@|$HOME|g" \
    "$(dirname "$0")/oit-portal.service.template" \
  | sudo tee /etc/systemd/system/oit-portal.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now oit-portal.service
systemctl --no-pager --full status oit-portal.service || true

# 预创建日志目录（避免 oit-portal 启动时遇到权限问题）
mkdir -p "$CFG_DIR/logs"

# ── 4. 立即试跑一次 ─────────────────────────────────────────
echo "==> [6/7] 试跑登录（当前 WiFi 为校园网时才会真正登录）"
oit-portal once || true

echo "==> [7/7] 完成"

cat <<'TIP'

✅ 安装完成！daemon 已作为 systemd 系统服务运行，开机自启 + 崩溃自动重启。

常用操作：
   systemctl status oit-portal          查看服务状态
   journalctl -u oit-portal -f          实时日志（stdout/stderr）
   oit-portal status / once / stop      与往常一样
日志文件: ~/.config/oit-portal/logs/oit-portal.log

WiFi SSID 触发（可选，连上校园网 WiFi 时立即重登）:
   编辑 ~/.config/oit-portal/config.toml 的 wifi_ssid = "你的校园网SSID"
   需系统装有 NetworkManager（nmcli）或 wireless-tools（iwgetid），
   都没有则该功能静默失效，不影响登录。详见 docs/linux-setup.md
TIP
