# 本仓库相对上游的定制

基于上游 [yzhao062/vibesignal](https://github.com/yzhao062/vibesignal) @ `510fa4e`（v0.1.1）。
所有源码改动集中在 `vibesignal/widget.py`：

| 定制 | 说明 |
|---|---|
| 深色主题 | 卡片底 `#111827`，白色粗体主文字，高对比状态色；blocked/error 报警态同步换深色 wash |
| 透明度 | 0.97 → 0.95，保证白色桌面背景上文字更清楚 |
| 停靠位置 | 左下角 → 右上角（菜单栏下 12px、右边距 14px） |
| Dock 图标 | `scripts/render_icon.py` 生成高对比向量图标，启动时经 pyobjc 读取 `~/.local/share/vibesignal/dock-icon.png` 设置进程 Dock 图标 |
| Codex 额度 footer | 面板底部状态栏：Codex 5 小时和周窗口剩余比例，例如 `5h 57% (4h40m) · wk 64% (5d16h)`，白色粗体显示，每 5 分钟后台刷新 |

额度数据来源：

- 优先从 `~/.codex/auth.json` 读取 Codex ChatGPT 登录态 access token，调
  `https://chatgpt.com/backend-api/codex/usage`；
- 接口不可用时读取本机 `~/.codex/sessions/**/*.jsonl` 最新 `rate_limits`；
- UI 显示剩余比例（`100 - used_percent`）和 reset 倒计时。没有可用额度数据时 footer 留空，不影响状态面板。

## 安装

```bash
uv tool install --force --python-preference only-managed --python 3.13 \
  'vibesignal[macos] @ git+file:///Users/kris.gong/code/vibesignal'
# 推送到 GitHub 后可换成 git+https://github.com/<your-github>/vibesignal.git
```

必须用 uv 托管 Python（`--python-preference only-managed`）：Homebrew Python 不带 tkinter。

## 安装后步骤（每次重装 / 新机器）

1. **Tcl/Tk 符号链接**（uv 托管 Python 的 venv 找不到 `init.tcl`，重建 venv 后都要做一次）：

   ```bash
   PYLIB="$(dirname "$(sed -n 's/^home *= *//p' ~/.local/share/uv/tools/vibesignal/pyvenv.cfg)")/lib"
   ln -sfn "$PYLIB/tcl9.0" ~/.local/share/uv/tools/vibesignal/lib/tcl9.0
   ln -sfn "$PYLIB/tk9.0"  ~/.local/share/uv/tools/vibesignal/lib/tk9.0
   ```

2. **Dock 图标资产**：

   ```bash
   mkdir -p ~/.local/share/vibesignal
   cp assets/dock-icon.png assets/VibeSignal.icns ~/.local/share/vibesignal/
   ```

   想换图案：改 `scripts/render_icon.py` 里的绘制参数重新生成；`.app` 启动器的图标是把
   `assets/VibeSignal.icns` 覆盖到 `~/Applications/VibeSignal.app/Contents/Resources/applet.icns`
   后 `codesign --force --sign -` 重签。

3. **启动器与自启**：`vibesignal install-launcher && vibesignal install-autostart`

4. **客户端 hooks**：
   - Claude Code：`hooks/claude-settings.snippet.json` 合并进 `~/.claude/settings.json`（命令建议写
     `~/.local/bin/vibesignal` 绝对路径，LaunchAgent/hook 环境的 PATH 不含 `~/.local/bin`）；
   - Codex：`hooks/codex-hooks.snippet.json` 合并进 `~/.codex/hooks.json`，之后在 Codex 会话里执行
     `/hooks` 信任新钩子。Codex 无 SessionEnd 事件，会话行靠 TTL 过期。

## Cowork 桥接（scripts/cowork-vibesignal-bridge）

Cowork（Claude.app 客户端）的 agent 跑在本地 Linux VM（claudevm）里，宿主机 hooks 够不到。
`scripts/cowork-vibesignal-bridge` 是宿主机侧的 watcher 守护进程，用两个信号近似出状态行：

1. **VM 进程 CPU**（主信号）：`com.apple.Virtualization.VirtualMachine` 进程 %cpu ≥ 5%
   视为在干活（热备闲置基线 ~0.5%；ps 的 %cpu 是衰减均值，自带平滑）；
2. **会话存储写入**（辅助信号）：`local-agent-mode-sessions/` 下的文件变动，
   排除 `rpm/` 心跳和 `skills-plugin/` 同步噪声。

任一信号在 180s 窗口内 → 面板显示 `cowork/local-vm working`；持续静默 → 转 done（随 TTL 消失）。
局限：单聚合行，blocked 等 VM 内部状态观测不到。

安装：

```bash
cp scripts/cowork-vibesignal-bridge ~/.local/bin/ && chmod +x ~/.local/bin/cowork-vibesignal-bridge
cp scripts/io.github.yzhao062.vibesignal.cowork-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.github.yzhao062.vibesignal.cowork-bridge.plist
```

调参（plist 里加 EnvironmentVariables）：`COWORK_BRIDGE_QUIET`（静默阈值秒）、
`COWORK_BRIDGE_CPU_MIN`（CPU 阈值）、`COWORK_BRIDGE_POLL`（轮询间隔）。
调试：`cowork-vibesignal-bridge --once` 单次判定。

## 与上游同步

```bash
git fetch upstream && git rebase upstream/main
# 冲突大概率集中在 vibesignal/widget.py 的定制块
```
