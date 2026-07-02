# VibeSignal

VibeSignal 是一个给 AI 编码工具用的桌面状态面板和 USB 状态灯控制器。它把 Claude Code、Codex 等本机会话的状态收集到同一个本地状态库里：工具正在工作时显示 working，需要你处理权限或输入时显示 blocked，完成一轮后显示 done。

源码仓库：<https://github.com/gt11799/vibesignal>

本仓库基于上游 `yzhao062/vibesignal` 做了本地化定制，重点是把桌面面板做得更适合长期常驻使用，并增加 Codex 剩余额度信息的展示。

## 主要特性

- 桌面浮窗：始终置顶、可拖拽、右键退出，读取同一份会话状态。
- 页面美化：深色主题、右上角停靠、更低透明度、blocked/error 高亮报警态。
- Claude Code 支持：通过 hooks 自动上报 working、blocked、done 和 SessionEnd。
- Codex 进程支持：通过 Codex hooks 把本地 Codex 会话纳入同一个状态面板。
- Codex 剩余额度展示：面板底部显示 5 小时窗口和周窗口的剩余比例与重置倒计时。
- Cowork 桥接：可把 Claude.app Cowork 本地 VM 的活动近似显示为 `cowork/local-vm`。
- 多会话聚合：多个 agent 同时跑时按 `blocked > error > done > working > idle` 聚合。
- 多种展示方式：USB busylight、终端 watch 面板、Tk 桌面 widget。

## 安装

推荐在 macOS 上使用 `uv` 托管 Python 安装。Homebrew Python 常见问题是缺少可用的 Tkinter，而 `uv --python-preference only-managed` 会使用自带 Tk 的 CPython。

```bash
uv tool install --force --python-preference only-managed --python 3.13 \
  'vibesignal[macos] @ git+https://github.com/gt11799/vibesignal.git'
```

安装后确认命令可用：

```bash
vibesignal status
```

如果使用的是 Windows 或 Linux，可以用普通 pip 安装，但桌面 widget 仍需要系统里有可用的 Tk：

```bash
pip install 'vibesignal @ git+https://github.com/gt11799/vibesignal.git'
```

## macOS 初始化

安装后建议执行这些步骤，让面板可以像普通应用一样启动并开机自启：

```bash
cp scripts/vibesignal-restyle ~/.local/bin/
chmod +x ~/.local/bin/vibesignal-restyle
~/.local/bin/vibesignal-restyle

mkdir -p ~/.local/share/vibesignal
cp assets/dock-icon.png assets/VibeSignal.icns ~/.local/share/vibesignal/

vibesignal install-launcher
vibesignal install-autostart
```

`vibesignal-restyle` 会修复 uv tool venv 里 Tcl/Tk 路径找不到的问题。每次 `uv tool install --force` 或升级后，都建议重新跑一次。

## 常用命令

```bash
vibesignal widget          # 启动桌面浮窗
vibesignal watch           # 在终端查看实时会话表
vibesignal status          # 查看当前聚合状态
vibesignal clear           # 清空所有会话状态
vibesignal off             # 清空状态并关闭 USB 灯
```

也可以手动写入一条状态，用于测试：

```bash
echo '{"session_id":"demo","cwd":"'$PWD'"}' \
  | vibesignal event --agent claude --state working
```

## 配置 Claude Code

把 `hooks/claude-settings.snippet.json` 合并到 `~/.claude/settings.json` 的 `hooks` 字段里。建议把 snippet 里的 `vibesignal` 命令改成绝对路径，例如：

```bash
~/.local/bin/vibesignal
```

Claude Code hooks 覆盖这些事件：

- `UserPromptSubmit`：标记为 working。
- `PostToolUse`：工具调用后回到 working。
- `Notification permission_prompt`：标记为 blocked。
- `Notification idle_prompt`、`Stop`、`StopFailure`：标记为 done。
- `SessionEnd`：立即清除结束的会话。

验证：

```bash
echo '{"session_id":"claude-test"}' \
  | ~/.local/bin/vibesignal event --agent claude --state working --quiet
~/.local/bin/vibesignal status
echo '{"session_id":"claude-test"}' \
  | ~/.local/bin/vibesignal end --agent claude --quiet
```

## 配置 Codex

把 `hooks/codex-hooks.snippet.json` 合并到 `~/.codex/hooks.json`。如果 hook 环境找不到 `vibesignal`，同样把命令改成绝对路径。

Codex hooks 覆盖这些事件：

- `UserPromptSubmit`：标记为 working。
- `PostToolUse`：保持 working。
- `PermissionRequest`：标记为 blocked。
- `Stop`：标记为 done。

合并后重启 Codex，并在 Codex 会话里执行 `/hooks`，信任新增的 VibeSignal hooks。
未信任的 command hooks 会被 Codex 跳过；信任后再跑一轮 Codex 对话，`vibesignal status`
应该能看到 `codex/<session>`。

## Codex 剩余额度展示

桌面面板底部会尝试显示：

```text
5h 57% (4h40m) · wk 64% (5d16h)
```

数据来源：

- 读取 `~/.codex/auth.json` 里的 Codex ChatGPT 登录态 access token。
- 优先请求 Codex 的 ChatGPT 后端 usage 接口；接口不可用时，读取本机 `~/.codex/sessions/**/*.jsonl` 里最新的 `rate_limits`。
- 面板显示的是剩余比例：`100 - used_percent`，并附带 reset 倒计时。

如果没有登录 Codex，且本机还没有带 `rate_limits` 的 Codex session 日志，footer 会留空，不影响会话状态展示。

## Cowork 桥接

Claude.app 的 Cowork 会话跑在本地 VM 里，宿主机 hooks 不能直接观察 VM 内部状态。本仓库提供 `scripts/cowork-vibesignal-bridge`，通过 VM 进程 CPU 和本地会话文件活动近似判断 Cowork 是否在工作。

安装：

```bash
cp scripts/cowork-vibesignal-bridge ~/.local/bin/
chmod +x ~/.local/bin/cowork-vibesignal-bridge
cp scripts/io.github.yzhao062.vibesignal.cowork-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.github.yzhao062.vibesignal.cowork-bridge.plist
```

调试：

```bash
cowork-vibesignal-bridge --once
```

更多迁移和排障步骤见 [INSTALL.md](INSTALL.md)，相对上游的定制说明见 [CUSTOMIZATIONS.md](CUSTOMIZATIONS.md)。

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,macos]'
pytest
```

项目入口在 `vibesignal/__main__.py`，桌面面板在 `vibesignal/widget.py`，状态解析逻辑在 `vibesignal/resolve.py`。

## 许可证

本项目沿用上游的 BSD-2-Clause License，详见 [LICENSE](LICENSE)。
