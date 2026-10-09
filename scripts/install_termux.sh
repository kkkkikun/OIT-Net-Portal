#!/data/data/com.termux/files/usr/bin/bash
# OIT 校园网自动登录 — Termux 一键安装
# 用法：把项目复制到手机（或 git clone）后，在 Termux 中进入项目目录执行：
#   bash scripts/install_termux.sh
set -eu

err() { echo "错误：$*" >&2; exit 1; }

# ── 0. 环境检查 ─────────────────────────────────────────────
command -v pkg >/dev/null || err "请在 Termux 中运行本脚本（找不到 pkg）"
echo "==> [1/6] 安装 Python（已装则跳过）"
command -v python >/dev/null || pkg install -y python

# ── 1. 安装本项目 ───────────────────────────────────────────
echo "==> [2/6] 安装 oit-portal 及依赖"
pip install --quiet .

# ── 2. 配置文件 ─────────────────────────────────────────────
CFG_DIR="${HOME}/.config/oit-portal"
mkdir -p "$CFG_DIR"
echo "==> [3/6] 生成配置 $CFG_DIR"
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

echo "==> [4/6] 写入凭据（密码只存本机，权限 600）"
read -rsp "请输入校园网密码（输入不回显）: " PASSWORD; echo
# 用 chmod 直接收紧权限（不用 umask 177，避免 umask 污染到
# 后续 oit-portal 子进程导致日志目录创建失败）
printf 'password = "%s"\n' "$PASSWORD" > "$CFG_DIR/credentials.toml"
chmod 600 "$CFG_DIR/credentials.toml"
unset PASSWORD

# ── 3. 开机自启（Termux:Boot）──────────────────────────────
echo "==> [5/6] 部署开机启动脚本"
if [ ! -d "${HOME}/.termux/boot" ]; then
  if command -v termux-setup-storage >/dev/null 2>&1; then :; fi
  mkdir -p "${HOME}/.termux/boot"
fi
sed "s|@PREFIX@|${PREFIX}|g" "$(dirname "$0")/boot_start.sh.template" \
  > "${HOME}/.termux/boot/oit-portal"
chmod +x "${HOME}/.termux/boot/oit-portal"

# 预创建日志目录（避免 oit-portal 启动时遇到权限问题）
mkdir -p "$CFG_DIR/logs"

# ── 4. 立即试跑一次 ─────────────────────────────────────────
echo "==> [6/6] 试跑登录（当前 WiFi 为校园网时才会真正登录）"
oit-portal once || true

cat <<'TIP'

✅ 安装完成！请务必完成以下两步，否则手机重启/锁屏后可能失效：

1) 电池优化豁免（关键）：
   设置 → 应用 → Termux → 电池/耗电管理 → 选择「不受限制 / 无限制」
   Termux:Boot 应用同样设置一次。
   国产 ROM（MIUI/ColorOS/EMUI 等）额外把两个应用加入「自启动」白名单。

2) 激活 Termux:Boot：
   确保已从 F-Droid 安装 Termux:Boot，并手动打开它一次（打开即激活监听）。

之后手机重启会自动登录；平时可随时运行：
   oit-portal status   查看状态
   oit-portal daemon   手动前台跑守护
   oit-portal stop     停止守护
日志：~/.config/oit-portal/logs/oit-portal.log
     （若 home 不可写会自动退化到 $TMPDIR/oit-portal/）
TIP
