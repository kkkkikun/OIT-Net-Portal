#!/usr/bin/env bash
# 在当前 Linux 架构构建离线安装包；Jetson/aarch64 请在目标架构原生执行。
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(uname -s)" = "Linux" ] || { echo "错误：请在 Linux 上构建" >&2; exit 1; }
command -v python3 >/dev/null || { echo "错误：需要 python3" >&2; exit 1; }
command -v tar >/dev/null || { echo "错误：需要 tar" >&2; exit 1; }
python3 -m pip --version >/dev/null || { echo "错误：需要 python3-pip" >&2; exit 1; }

ARCH="$(uname -m)"
PACKAGE="oit-portal-linux-$ARCH"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
PKG_DIR="$STAGING/$PACKAGE"
mkdir -p "$PKG_DIR/wheelhouse" "$ROOT/dist"

echo "==> 收集 $ARCH 离线依赖（构建阶段需要联网或已有 pip 缓存）"
python3 -m pip wheel --timeout 60 --wheel-dir "$PKG_DIR/wheelhouse" "$ROOT"

cp "$ROOT/scripts/install_linux.sh" "$PKG_DIR/install.sh"
cp "$ROOT/scripts/uninstall_linux.sh" "$PKG_DIR/uninstall.sh"
cp "$ROOT/scripts/oit-portal.service.template" "$PKG_DIR/oit-portal.service.template"
cp "$ROOT/config.example.toml" "$PKG_DIR/config.example.toml"
cp "$ROOT/docs/linux-setup.md" "$PKG_DIR/README.md"
chmod +x "$PKG_DIR/install.sh" "$PKG_DIR/uninstall.sh"
{
  echo "architecture=$ARCH"
  echo "build_python=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
  echo "target=systemd Linux; target Python must be compatible with bundled wheels"
} > "$PKG_DIR/BUILD-INFO"

ARCHIVE="$ROOT/dist/$PACKAGE.tar.gz"
tar -C "$STAGING" -czf "$ARCHIVE" "$PACKAGE"
(
  cd "$ROOT/dist"
  sha256sum "$PACKAGE.tar.gz" > "$PACKAGE.tar.gz.sha256"
)

echo "==> 包内容"
tar -tzf "$ARCHIVE"
echo "构建完成：$ARCHIVE"
echo "校验文件：$ARCHIVE.sha256"
