# 安卓（Termux）部署指南

## 前置要求

1. **必须从 F-Droid 安装**（Google Play 版 Termux 已停止更新且与 Termux:Boot 不兼容）：
   - [Termux](https://f-droid.org/packages/com.termux/)
   - [Termux:Boot](https://f-droid.org/packages/com.termux.boot/)
2. 手机能访问项目文件（电脑 `git clone` 后用任意方式传入手机，如 LocalSend / USB / 网盘）

## 安装步骤

```bash
# 1. 进入 Termux，把项目放到手机上后进入目录
cd ~/OIT-Net-Portal

# 2. 一键安装（装依赖 + 写配置 + 部署开机自启 + 试跑）
bash scripts/install_termux.sh
```

安装脚本会依次：装 Python → `pip install .` → 生成 `~/.config/oit-portal/config.toml`（询问账号）→
写 `credentials.toml`（询问密码，600 权限）→ 部署 `~/.termux/boot/oit-portal` → 试跑一次 `oit-portal once`。

## ⚠️ 必做的两步手动设置（不做则重启/锁屏后失效）

1. **电池优化豁免**：设置 → 应用 → Termux → 电池 → **不受限制**；Termux:Boot 同样设置。
   国产 ROM（MIUI / ColorOS / EMUI 等）还需在「自启动管理」中放行这两个应用。
2. **激活 Termux:Boot**：安装后**手动打开一次 Termux:Boot 应用**（打开即开始监听开机广播）。

## 验证

```bash
oit-portal status        # online / captive / offline 三态
oit-portal once          # 手动登录一次
oit-portal daemon        # 前台跑守护（观察日志）
oit-portal stop          # 停止
```

- **重启手机**：2 分钟内应自动完成校园网登录（无需亮屏操作）
- **锁屏过夜**：wake-lock 保证 CPU 不冻结；若仍被系统冻结，检查电池豁免是否生效
- 日志：`~/.local/state/oit-portal/oit-portal.log`

## 常见问题

| 现象 | 处理 |
|------|------|
| 重启后没自动登录 | Termux:Boot 没打开过一次；或 ROM 杀后台 → 检查两步手动设置 |
| 锁屏后掉线 | 电池优化未豁免；MIUI 等需锁定 Termux 后台任务（最近任务上锁） |
| `termux-wake-lock: not found` | `pkg install termux-tools` |
| 想看实时日志 | `tail -f ~/.local/state/oit-portal/oit-portal.log` |
| 需要验证码时 | `oit-portal login-info` 查看人工登录引导，浏览器登一次后 daemon 自动收割会话 |
